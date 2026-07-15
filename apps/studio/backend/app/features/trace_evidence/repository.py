"""Physical selection boundary for cohesive trace evidence."""

from __future__ import annotations

from app.features.otel_spans import repository as span_repository


async def get_trace(trace_id: str) -> list[dict]:
    """Select a complete trace without interpreting its evidence."""
    return await span_repository.get_fused_trace_spans(trace_id)
