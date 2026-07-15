"""Assemble complete normalized spans and verified executable annotations."""

from __future__ import annotations

from typing import Any, Literal

from app.features.agent_diagnostics.assembler import assemble_agent_detail
from app.features.agent_diagnostics.contract import AgentEvidenceError
from app.features.store_diagnostics.schemas import EvidenceDiagnostic
from app.features.trace_evidence.schemas import (
    AgentExecutableAnnotation,
    ExecutableRelationships,
    NormalizedSpanEvidence,
    StoreAnnotation,
    TraceEvidence,
    TraceEvidenceDiagnostic,
    WorkflowExecutableAnnotation,
)
from app.features.workflow_diagnostics.assembler import (
    WorkflowEvidenceError,
    assemble_workflow_store_diagnostic,
)


def _attributes(span: dict[str, Any]) -> dict[str, Any]:
    attributes = span.get("attributes_json")
    return attributes if isinstance(attributes, dict) else {}


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _diagnostic(
    *,
    scope: Literal["trace", "executable"],
    owner_span_id: str | None,
    code: str,
    path: str,
    message: str,
) -> TraceEvidenceDiagnostic:
    return TraceEvidenceDiagnostic(
        scope=scope,
        owner_span_id=owner_span_id,
        issue=EvidenceDiagnostic(code=code, path=path, message=message),
    )


def _semantic_error_diagnostics(
    *,
    owner_span_id: str,
    error: AgentEvidenceError | WorkflowEvidenceError,
) -> list[TraceEvidenceDiagnostic]:
    issues = error.diagnostics or [
        EvidenceDiagnostic(code=error.code, path="executable", message=error.message)
    ]
    return [
        TraceEvidenceDiagnostic(scope="executable", owner_span_id=owner_span_id, issue=issue)
        for issue in issues
    ]


def assemble_trace_evidence(trace_id: str, trace_spans: list[dict[str, Any]]) -> TraceEvidence:
    """Keep every raw span while enriching supported executable owners."""
    spans = [NormalizedSpanEvidence.model_validate(span) for span in trace_spans]
    executables: dict[str, Any] = {}
    operations: dict[str, dict[str, Any]] = {}
    stores: dict[str, StoreAnnotation] = {}
    relationships: dict[str, ExecutableRelationships] = {}
    diagnostics: list[TraceEvidenceDiagnostic] = []

    for span in trace_spans:
        owner_span_id = span.get("span_id")
        if not isinstance(owner_span_id, str):
            continue
        if span.get("trace_id") != trace_id:
            diagnostics.append(
                _diagnostic(
                    scope="trace",
                    owner_span_id=None,
                    code="trace_identity_mismatch",
                    path=f"span[{owner_span_id}].trace_id",
                    message="Span trace identity does not match the requested trace.",
                )
            )

        attributes = _attributes(span)
        executable_type = attributes.get("junjo.span_type")
        if executable_type == "agent":
            try:
                detail = assemble_agent_detail(span, trace_spans)
            except AgentEvidenceError as error:
                diagnostics.extend(
                    _semantic_error_diagnostics(owner_span_id=owner_span_id, error=error)
                )
                continue

            runtime_id = detail.summary.runtime_id
            store_id = detail.state.store_id if detail.state.available else None
            executables[owner_span_id] = AgentExecutableAnnotation(
                executable_type="agent",
                owner_span_id=owner_span_id,
                runtime_id=runtime_id,
                store_id=store_id,
                unavailable_store=None if detail.state.available else detail.state,
                summary=detail.summary,
                definition=detail.definition,
                input=detail.input,
                output=detail.output,
                input_candidate=detail.input_candidate,
                history_candidate=detail.history_candidate,
                error=detail.error,
                cancellation=detail.cancellation,
                integrity=detail.integrity,
            )
            operations[runtime_id] = {
                operation.span_id: operation for operation in detail.operations
            }
            relationships[owner_span_id] = ExecutableRelationships(
                parent=detail.parent_executable,
                nested=detail.nested_executables,
            )
            diagnostics.extend(
                TraceEvidenceDiagnostic(
                    scope="executable",
                    owner_span_id=owner_span_id,
                    issue=issue,
                )
                for issue in detail.integrity.diagnostics
            )
            if store_id is not None:
                if store_id in stores:
                    diagnostics.append(
                        _diagnostic(
                            scope="trace",
                            owner_span_id=None,
                            code="duplicate_store_identity",
                            path=f"stores.{store_id}",
                            message="More than one executable owns the same Store ID.",
                        )
                    )
                else:
                    stores[store_id] = StoreAnnotation(
                        store_id=store_id,
                        owner_span_id=owner_span_id,
                        owner_runtime_id=runtime_id,
                        owner_executable_type="agent",
                        detail=detail.state,
                        integrity=detail.integrity,
                    )
            continue

        if executable_type not in {"workflow", "subflow"}:
            continue
        try:
            detail = assemble_workflow_store_diagnostic(span, trace_spans)
        except WorkflowEvidenceError as error:
            diagnostics.extend(
                _semantic_error_diagnostics(owner_span_id=owner_span_id, error=error)
            )
            continue

        runtime_id = _optional_string(attributes.get("junjo.executable_runtime_id"))
        store_id = detail.state.store_id if detail.state.available else None
        executables[owner_span_id] = WorkflowExecutableAnnotation(
            executable_type=detail.executable_type,
            owner_span_id=owner_span_id,
            name=detail.name,
            definition_id=_optional_string(attributes.get("junjo.executable_definition_id")),
            runtime_id=runtime_id,
            structural_id=_optional_string(attributes.get("junjo.executable_structural_id")),
            store_id=store_id,
            unavailable_store=None if detail.state.available else detail.state,
            integrity=detail.integrity,
        )
        diagnostics.extend(
            TraceEvidenceDiagnostic(
                scope="executable",
                owner_span_id=owner_span_id,
                issue=issue,
            )
            for issue in detail.integrity.diagnostics
        )
        if store_id is not None:
            if store_id in stores:
                diagnostics.append(
                    _diagnostic(
                        scope="trace",
                        owner_span_id=None,
                        code="duplicate_store_identity",
                        path=f"stores.{store_id}",
                        message="More than one executable owns the same Store ID.",
                    )
                )
            else:
                stores[store_id] = StoreAnnotation(
                    store_id=store_id,
                    owner_span_id=owner_span_id,
                    owner_runtime_id=runtime_id,
                    owner_executable_type=detail.executable_type,
                    detail=detail.state,
                    integrity=detail.integrity,
                )

    return TraceEvidence(
        trace_id=trace_id,
        spans=spans,
        executables_by_span_id=executables,
        operations_by_owner_runtime_id=operations,
        stores_by_id=stores,
        relationships_by_owner_span_id=relationships,
        diagnostics=diagnostics,
    )
