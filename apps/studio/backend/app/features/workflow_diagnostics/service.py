"""Application service for Workflow Store diagnostics."""

from __future__ import annotations

from app.features.workflow_diagnostics import repository
from app.features.workflow_diagnostics.assembler import (
    assemble_workflow_store_diagnostic,
)
from app.features.workflow_diagnostics.schemas import WorkflowStoreDiagnostic


async def get_workflow_store(
    trace_id: str,
    workflow_span_id: str,
) -> WorkflowStoreDiagnostic | None:
    """Return one owner-scoped Workflow Store projection."""
    spans = await repository.get_workflow_trace(trace_id)
    owner = next(
        (
            span
            for span in spans
            if span.get("span_id") == workflow_span_id
            and isinstance(span.get("attributes_json"), dict)
        ),
        None,
    )
    if owner is None:
        return None
    return assemble_workflow_store_diagnostic(owner, spans)
