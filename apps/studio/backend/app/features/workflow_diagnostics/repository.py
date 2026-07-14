"""Physical selection boundary for Workflow semantic diagnostics."""

from __future__ import annotations

from app.features.otel_spans import repository as span_repository


async def get_workflow_trace(trace_id: str) -> list[dict]:
    """Select the complete trace needed for Store-ID scoped reconstruction."""
    return await span_repository.get_fused_trace_spans(trace_id)
