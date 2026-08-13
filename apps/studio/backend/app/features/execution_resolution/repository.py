"""Physical selection boundary for semantic execution resolution."""

from __future__ import annotations

from app.features.execution_resolution.schemas import ExecutableType
from app.features.otel_spans import repository as span_repository


async def list_owner_candidates(
    *,
    service_name: str,
    executable_type: ExecutableType,
    runtime_id: str,
) -> list[dict]:
    return await span_repository.get_fused_executable_spans(
        service_name=service_name,
        executable_type=executable_type,
        runtime_id=runtime_id,
    )


async def list_trace_spans(trace_id: str) -> list[dict]:
    """Return one resolved execution's trace for detail-route selection."""

    return await span_repository.get_fused_trace_spans(trace_id)
