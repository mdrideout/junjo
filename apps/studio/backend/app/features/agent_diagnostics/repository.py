"""Physical span selection boundary for Agent diagnostics."""

from __future__ import annotations

from app.features.otel_spans import repository as span_repository


async def list_agent_owner_spans(service_name: str) -> list[dict]:
    """Select recent Agent owner spans without interpreting their semantics."""
    return await span_repository.get_fused_agent_spans(service_name)


async def get_agent_trace(trace_id: str) -> list[dict]:
    """Select the complete trace needed for owner-scoped semantic assembly."""
    return await span_repository.get_fused_trace_spans(trace_id)
