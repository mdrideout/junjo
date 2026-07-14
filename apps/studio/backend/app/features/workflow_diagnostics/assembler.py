"""Assemble one Workflow Store diagnostic from preserved OTLP evidence."""

from __future__ import annotations

from typing import Any, Literal

from app.features.store_diagnostics.integrity import assemble_evidence_integrity
from app.features.store_diagnostics.reconstruction import (
    WORKFLOW_STORE_BOUNDARY,
    reconstruct_store,
)
from app.features.store_diagnostics.schemas import EvidenceDiagnostic
from app.features.telemetry_contract.scalars import (
    ACTIVE_TELEMETRY_CONTRACT_VERSION,
    is_active_contract_version,
    is_portable_enum,
    is_portable_text,
    portable_diagnostic_text,
    span_evidence_path,
)
from app.features.workflow_diagnostics.schemas import WorkflowStoreDiagnostic


class WorkflowEvidenceError(Exception):
    """A Workflow span cannot produce a supported semantic projection."""

    def __init__(
        self,
        code: Literal["unsupported_contract", "unidentifiable_workflow"],
        message: str,
        diagnostics: list[EvidenceDiagnostic] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.diagnostics = diagnostics or []


def _diagnostic(code: str, path: str, message: str) -> EvidenceDiagnostic:
    return EvidenceDiagnostic(
        code=portable_diagnostic_text(code, fallback="invalid_evidence"),
        path=portable_diagnostic_text(path, fallback="evidence"),
        message=portable_diagnostic_text(
            message,
            fallback="Evidence contains nonportable diagnostic text.",
        ),
    )


def _attributes(span: dict[str, Any]) -> dict[str, Any]:
    value = span.get("attributes_json")
    return value if isinstance(value, dict) else {}


def _store_evidence_spans(
    owner_span: dict[str, Any],
    trace_spans: list[dict[str, Any]],
    store_id: Any,
) -> tuple[list[dict[str, Any]], list[EvidenceDiagnostic]]:
    """Select only the owner and spans carrying events for its Store ID."""
    selected = [owner_span]
    diagnostics: list[EvidenceDiagnostic] = []
    for span in trace_spans:
        if span is owner_span:
            continue
        events = span.get("events_json")
        if not isinstance(events, list):
            continue
        carries_store_evidence = any(
            isinstance(event, dict)
            and event.get("name") == "set_state"
            and isinstance(event.get("attributes"), dict)
            and event["attributes"].get("junjo.store.id") == store_id
            for event in events
        )
        if not carries_store_evidence:
            continue
        attributes = _attributes(span)
        version = attributes.get("junjo.telemetry.contract_version")
        if not is_active_contract_version(version):
            code = "missing_contract_version" if version is None else "unsupported_contract"
            diagnostics.append(
                _diagnostic(
                    code,
                    span_evidence_path(span, "junjo.telemetry.contract_version"),
                    (
                        "Store event evidence is missing its telemetry contract version."
                        if version is None
                        else "Store event evidence uses an unsupported telemetry contract."
                    ),
                )
            )
            continue
        selected.append(span)
    return selected, diagnostics


def assemble_workflow_store_diagnostic(
    owner_span: dict[str, Any],
    trace_spans: list[dict[str, Any]],
) -> WorkflowStoreDiagnostic:
    """Validate one Workflow owner and independently reconstruct its Store."""
    attributes = _attributes(owner_span)
    executable_type = attributes.get("junjo.span_type")
    if not is_portable_enum(executable_type, {"workflow", "subflow"}):
        raise WorkflowEvidenceError(
            "unidentifiable_workflow",
            "The selected span is not a Workflow or Subflow owner.",
        )
    version = attributes.get("junjo.telemetry.contract_version")
    if not is_active_contract_version(version):
        issue = _diagnostic(
            "unsupported_contract",
            "junjo.telemetry.contract_version",
            (
                f"Expected telemetry contract {ACTIVE_TELEMETRY_CONTRACT_VERSION}; "
                f"observed {version!r}."
            ),
        )
        raise WorkflowEvidenceError("unsupported_contract", issue.message, [issue])

    trace_id = owner_span.get("trace_id")
    span_id = owner_span.get("span_id")
    name = owner_span.get("name")
    if not (
        isinstance(trace_id, str)
        and isinstance(span_id, str)
        and is_portable_text(name, nonempty=True)
    ):
        issue = _diagnostic(
            "required_identity_missing",
            "workflow.identity",
            "Workflow trace, span, or name identity is invalid.",
        )
        raise WorkflowEvidenceError("unidentifiable_workflow", issue.message, [issue])

    evidence_spans, diagnostics = _store_evidence_spans(
        owner_span,
        trace_spans,
        attributes.get(WORKFLOW_STORE_BOUNDARY.store_id_attribute),
    )
    reconstruction = reconstruct_store(
        attributes,
        evidence_spans,
        WORKFLOW_STORE_BOUNDARY,
    )
    diagnostics.extend(reconstruction.diagnostics)
    integrity = assemble_evidence_integrity(evidence_spans, diagnostics)
    try:
        return WorkflowStoreDiagnostic(
            trace_id=trace_id,
            workflow_span_id=span_id,
            executable_type=executable_type,
            name=name,
            state=reconstruction.detail,
            integrity=integrity,
        )
    except ValueError as error:
        issue = _diagnostic(
            "invalid_workflow_projection",
            "workflow.store",
            str(error),
        )
        raise WorkflowEvidenceError(
            "unidentifiable_workflow",
            "Workflow Store evidence cannot be represented.",
            [issue],
        ) from error
