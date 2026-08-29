"""Assemble complete normalized spans and verified executable annotations."""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote

from app.features.agent_diagnostics.assembler import assemble_agent_detail
from app.features.agent_diagnostics.contract import AgentEvidenceError
from app.features.store_diagnostics.schemas import EvidenceDiagnostic
from app.features.trace_evidence.schemas import (
    AgentExecutableAnnotation,
    AttemptEvidenceManifest,
    AttemptEvidenceSubject,
    ExecutableManifestEntry,
    ExecutableRelationships,
    FailureSpanManifestEntry,
    NormalizedSpanEvidence,
    OperationManifestEntry,
    SelectedSpanEvidence,
    SelectedSpanEvidenceResponse,
    SemanticSpanKind,
    SpanManifestEntry,
    StoreAnnotation,
    StoreManifestEntry,
    TraceEvidence,
    TraceEvidenceDiagnostic,
    TraceManifestSummary,
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


def _semantic_kind(span: NormalizedSpanEvidence) -> SemanticSpanKind:
    attributes = span.attributes_json
    operation_type = attributes.get("junjo.agent.operation_type")
    if operation_type == "model_request":
        return "model"
    if operation_type == "tool":
        return "tool"
    span_type = attributes.get("junjo.span_type")
    if span_type in {"agent", "workflow", "subflow", "node", "run_concurrent"}:
        return span_type
    gen_ai_operation = attributes.get("gen_ai.operation.name")
    if gen_ai_operation in {"chat", "text_completion", "generate_content", "responses"}:
        return "model"
    if gen_ai_operation == "execute_tool":
        return "tool"
    if gen_ai_operation == "invoke_agent":
        return "agent"
    if gen_ai_operation == "invoke_workflow":
        return "workflow"
    openinference_kind = attributes.get("openinference.span.kind")
    if isinstance(openinference_kind, str):
        if openinference_kind.upper() == "LLM":
            return "model"
        if openinference_kind.upper() == "TOOL":
            return "tool"
    return "span"


def _operation_name(span: NormalizedSpanEvidence, semantic_kind: SemanticSpanKind) -> str:
    attributes = span.attributes_json
    if semantic_kind == "model":
        candidates = (
            attributes.get("junjo.agent.model.name"),
            attributes.get("gen_ai.response.model"),
            attributes.get("gen_ai.request.model"),
            attributes.get("llm.model_name"),
        )
    else:
        candidates = (
            attributes.get("junjo.agent.tool.name"),
            attributes.get("gen_ai.tool.name"),
            attributes.get("tool.name"),
        )
    return next(
        (candidate for candidate in candidates if isinstance(candidate, str) and candidate),
        span.name,
    )


def _is_failed(span: NormalizedSpanEvidence) -> bool:
    if span.status_code.upper() in {"2", "ERROR", "STATUS_CODE_ERROR"}:
        return True
    if span.attributes_json.get("error.type"):
        return True
    return any(
        isinstance(event, dict) and event.get("name") in {"exception", "junjo.hook_error"}
        for event in span.events_json
    )


def _failure_fields(span: NormalizedSpanEvidence) -> tuple[str | None, str | None, bool]:
    exception_type = _optional_string(span.attributes_json.get("error.type"))
    exception_message = _optional_string(span.attributes_json.get("error.message"))
    has_stacktrace = False
    for event in span.events_json:
        if not isinstance(event, dict) or event.get("name") not in {
            "exception",
            "junjo.hook_error",
        }:
            continue
        attributes = event.get("attributes")
        if not isinstance(attributes, dict):
            continue
        exception_type = (
            _optional_string(attributes.get("exception.type"))
            or _optional_string(attributes.get("junjo.hook.error.type"))
            or exception_type
        )
        exception_message = (
            _optional_string(attributes.get("exception.message"))
            or _optional_string(attributes.get("junjo.hook.error.message"))
            or exception_message
        )
        if _optional_string(attributes.get("exception.stacktrace")) is not None:
            has_stacktrace = True
    return (
        exception_type,
        exception_message or _optional_string(span.status_message),
        has_stacktrace,
    )


def _operation_index(
    evidence: TraceEvidence,
) -> tuple[dict[str, tuple[str, Any]], dict[str, str]]:
    operations_by_span_id: dict[str, tuple[str, Any]] = {}
    owner_span_id_by_runtime_id = {
        executable.runtime_id: owner_span_id
        for owner_span_id, executable in evidence.executables_by_span_id.items()
        if executable.runtime_id is not None
    }
    for owner_runtime_id, operations in evidence.operations_by_owner_runtime_id.items():
        for span_id, operation in operations.items():
            operations_by_span_id[span_id] = (owner_runtime_id, operation)
    return operations_by_span_id, owner_span_id_by_runtime_id


def _nearest_executable_owner(
    *,
    span: NormalizedSpanEvidence,
    spans_by_id: dict[str, NormalizedSpanEvidence],
    executable_span_ids: set[str],
) -> str | None:
    if span.span_id in executable_span_ids:
        return span.span_id
    parent_span_id = span.parent_span_id
    visited: set[str] = set()
    while parent_span_id is not None and parent_span_id not in visited:
        if parent_span_id in executable_span_ids:
            return parent_span_id
        visited.add(parent_span_id)
        parent = spans_by_id.get(parent_span_id)
        if parent is None:
            return None
        parent_span_id = parent.parent_span_id
    return None


def assemble_attempt_evidence_manifest(
    *,
    subject: AttemptEvidenceSubject,
    evidence: TraceEvidence,
) -> AttemptEvidenceManifest:
    """Project one complete trace into a selectable, payload-light manifest."""
    encoded_service_name = quote(subject.reference.service_name, safe="")
    spans_by_id = {span.span_id: span for span in evidence.spans}
    operations_by_span_id, owner_span_id_by_runtime_id = _operation_index(evidence)
    executable_span_ids = set(evidence.executables_by_span_id)

    span_entries: list[SpanManifestEntry] = []
    failures: list[FailureSpanManifestEntry] = []
    for span in evidence.spans:
        failed = _is_failed(span)
        span_path = f"/traces/{encoded_service_name}/{evidence.trace_id}/{span.span_id}"
        semantic_kind = _semantic_kind(span)
        span_entries.append(
            SpanManifestEntry(
                span_id=span.span_id,
                parent_span_id=span.parent_span_id,
                name=span.name,
                semantic_kind=semantic_kind,
                status_code=span.status_code,
                start_time=span.start_time,
                end_time=span.end_time,
                failed=failed,
                span_path=span_path,
            )
        )
        if not failed:
            continue
        owner_runtime_id = None
        operation_entry = operations_by_span_id.get(span.span_id)
        if operation_entry is not None:
            owner_runtime_id = operation_entry[0]
            owner_span_id = owner_span_id_by_runtime_id.get(owner_runtime_id)
        else:
            owner_span_id = _nearest_executable_owner(
                span=span,
                spans_by_id=spans_by_id,
                executable_span_ids=executable_span_ids,
            )
            if owner_span_id is not None:
                owner_runtime_id = evidence.executables_by_span_id[owner_span_id].runtime_id
        exception_type, exception_message, has_stacktrace = _failure_fields(span)
        failures.append(
            FailureSpanManifestEntry(
                span_id=span.span_id,
                parent_span_id=span.parent_span_id,
                name=span.name,
                semantic_kind=semantic_kind,
                status_code=span.status_code,
                start_time=span.start_time,
                end_time=span.end_time,
                exception_type=exception_type,
                exception_message=exception_message,
                stacktrace_available=has_stacktrace,
                owner_span_id=owner_span_id,
                owner_runtime_id=owner_runtime_id,
                span_path=span_path,
            )
        )

    executables: list[ExecutableManifestEntry] = []
    for owner_span_id, executable in evidence.executables_by_span_id.items():
        owner_span = spans_by_id[owner_span_id]
        if isinstance(executable, AgentExecutableAnnotation):
            name = executable.summary.agent_name
            outcome = executable.summary.outcome
        else:
            name = executable.name
            outcome = "failed" if _is_failed(owner_span) else None
        executables.append(
            ExecutableManifestEntry(
                owner_span_id=owner_span_id,
                executable_type=executable.executable_type,
                name=name,
                runtime_id=executable.runtime_id,
                store_id=executable.store_id,
                outcome=outcome,
                status_code=owner_span.status_code,
                failed=_is_failed(owner_span),
                integrity=executable.integrity,
            )
        )

    operations: list[OperationManifestEntry] = []
    operation_span_ids: set[str] = set()
    for span in evidence.spans:
        semantic_kind = _semantic_kind(span)
        if semantic_kind not in {"model", "tool"} or span.span_id in operation_span_ids:
            continue
        operation_span_ids.add(span.span_id)
        operation_entry = operations_by_span_id.get(span.span_id)
        if operation_entry is not None:
            owner_runtime_id, operation = operation_entry
            owner_span_id = owner_span_id_by_runtime_id.get(owner_runtime_id)
            name = (
                operation.model_name
                if operation.operation_type == "model_request"
                else operation.tool_name
            )
            outcome = operation.outcome
            duration_ns = operation.duration_ns
            error_type = operation.error.type if operation.error else None
            error_message = operation.error.message if operation.error else None
        else:
            owner_span_id = _nearest_executable_owner(
                span=span,
                spans_by_id=spans_by_id,
                executable_span_ids=executable_span_ids,
            )
            owner_runtime_id = (
                evidence.executables_by_span_id[owner_span_id].runtime_id
                if owner_span_id is not None
                else None
            )
            name = _operation_name(span, semantic_kind)
            outcome = "failed" if _is_failed(span) else "completed"
            duration_ns = None
            error_type, error_message, _has_stacktrace = _failure_fields(span)
        operations.append(
            OperationManifestEntry(
                owner_span_id=owner_span_id,
                owner_runtime_id=owner_runtime_id,
                span_id=span.span_id,
                operation_type="model_request" if semantic_kind == "model" else "tool",
                name=name,
                outcome=outcome,
                duration_ns=duration_ns,
                error_type=error_type,
                error_message=error_message,
            )
        )

    stores: list[StoreManifestEntry] = []
    for owner_span_id, executable in evidence.executables_by_span_id.items():
        indexed_store = (
            evidence.stores_by_id.get(executable.store_id)
            if executable.store_id is not None
            else None
        )
        store = (
            indexed_store
            if indexed_store is not None and indexed_store.owner_span_id == owner_span_id
            else None
        )
        detail = store.detail if store is not None else executable.unavailable_store
        if detail is None:
            continue
        stores.append(
            StoreManifestEntry(
                store_id=store.store_id if store is not None else None,
                owner_span_id=owner_span_id,
                owner_runtime_id=executable.runtime_id,
                owner_executable_type=executable.executable_type,
                available=detail.available,
                transition_count=detail.transition_count,
                reconstructable=detail.reconstructable,
                reconstruction_status=detail.reconstruction_status,
                integrity=executable.integrity,
            )
        )
    return AttemptEvidenceManifest(
        subject=subject,
        trace=TraceManifestSummary(
            trace_id=evidence.trace_id,
            span_count=len(evidence.spans),
            root_span_ids=[span.span_id for span in evidence.spans if span.parent_span_id is None],
        ),
        spans=span_entries,
        failures=failures,
        executables=executables,
        operations=operations,
        stores=stores,
        relationships_by_owner_span_id=evidence.relationships_by_owner_span_id,
        diagnostics=evidence.diagnostics,
    )


def select_attempt_span_evidence(
    *,
    subject: AttemptEvidenceSubject,
    evidence: TraceEvidence,
    span_ids: list[str],
) -> SelectedSpanEvidenceResponse:
    """Return complete evidence for explicit span identities in caller order."""
    spans_by_id = {span.span_id: span for span in evidence.spans}
    operations_by_span_id, _owner_span_id_by_runtime_id = _operation_index(evidence)
    stores_by_owner_span_id: dict[str, list[StoreAnnotation]] = {}
    for store in evidence.stores_by_id.values():
        stores_by_owner_span_id.setdefault(store.owner_span_id, []).append(store)

    items: list[SelectedSpanEvidence] = []
    missing_span_ids: list[str] = []
    for span_id in span_ids:
        span = spans_by_id.get(span_id)
        if span is None:
            missing_span_ids.append(span_id)
            continue
        operation_entry = operations_by_span_id.get(span_id)
        items.append(
            SelectedSpanEvidence(
                span=span,
                executable=evidence.executables_by_span_id.get(span_id),
                operation=operation_entry[1] if operation_entry is not None else None,
                stores=stores_by_owner_span_id.get(span_id, []),
                relationships=evidence.relationships_by_owner_span_id.get(span_id),
                diagnostics=[
                    diagnostic
                    for diagnostic in evidence.diagnostics
                    if diagnostic.owner_span_id == span_id
                ],
            )
        )
    return SelectedSpanEvidenceResponse(
        subject=subject,
        items=items,
        missing_span_ids=missing_span_ids,
    )
