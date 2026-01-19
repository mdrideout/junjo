"""REST API endpoints for querying OTEL spans.

Provides SRP-compliant endpoints for span retrieval from the V4 two-tier
Parquet architecture (SQLite metadata index + DataFusion queries).
Each endpoint has a single, well-defined responsibility.

API Structure:
- /api/v1/observability/services
- /api/v1/observability/services/{serviceName}/spans
- /api/v1/observability/services/{serviceName}/spans/root
- /api/v1/observability/services/{serviceName}/workflows
- /api/v1/observability/traces/{traceId}/spans
- /api/v1/observability/traces/{traceId}/spans/{spanId}
"""

from typing import Any

from fastapi import APIRouter, Query
from loguru import logger

from app.features.otel_spans import repository

router = APIRouter()


@router.get("/services", response_model=list[str])
async def list_services() -> list[str]:
    """List all distinct service names.

    Returns:
        List of service names in alphabetical order.

    Example:
        GET /api/v1/observability/services
        → ["my-service", "another-service"]
    """
    logger.debug("Fetching distinct service names")
    return await repository.get_fused_distinct_service_names()


@router.get("/services/{service_name}/spans", response_model=list[dict[str, Any]])
async def get_service_spans(
    service_name: str,
    limit: int = Query(default=500, ge=1, le=10000, description="Maximum spans to return"),
) -> list[dict[str, Any]]:
    """Get all spans for a service.

    Args:
        service_name: Name of the service.
        limit: Maximum number of spans to return (default 500, max 10000).

    Returns:
        List of spans ordered by start time (most recent first).

    Example:
        GET /api/v1/observability/services/my-service/spans?limit=100
    """
    logger.debug(f"Fetching spans for service: {service_name}, limit: {limit}")
    return await repository.get_fused_service_spans(service_name, limit)


@router.get("/services/{service_name}/spans/root", response_model=list[dict[str, Any]])
async def get_root_spans(
    service_name: str,
    has_llm: bool = Query(default=False, description="Filter for traces containing LLM operations"),
    limit: int = Query(default=500, ge=1, le=10000, description="Maximum spans to return"),
) -> list[dict[str, Any]]:
    """Get root spans (no parent) for a service.

    Root spans are entry points to traces (parent_span_id IS NULL).

    Args:
        service_name: Name of the service.
        has_llm: If True, only return root spans from traces with LLM operations.
        limit: Maximum number of spans to return (default 500, max 10000).

    Returns:
        List of root spans ordered by start time (most recent first).

    Examples:
        GET /api/v1/observability/services/my-service/spans/root
        GET /api/v1/observability/services/my-service/spans/root?has_llm=true&limit=100
    """
    logger.debug(
        f"Fetching root spans for service: {service_name}, has_llm: {has_llm}, limit: {limit}"
    )

    if has_llm:
        return await repository.get_fused_root_spans_with_llm(service_name, limit)
    return await repository.get_fused_root_spans(service_name, limit)


@router.get("/services/{service_name}/workflows", response_model=list[dict[str, Any]])
async def get_workflow_spans(
    service_name: str,
    limit: int = Query(default=500, ge=1, le=10000, description="Maximum spans to return"),
) -> list[dict[str, Any]]:
    """Get workflow-type spans for a service.

    Filters spans where junjo_span_type = 'workflow'.

    Args:
        service_name: Name of the service.
        limit: Maximum number of spans to return (default 500, max 10000).

    Returns:
        List of workflow spans ordered by start time (most recent first).

    Example:
        GET /api/v1/observability/services/my-service/workflows?limit=50
    """
    logger.debug(f"Fetching workflow spans for service: {service_name}, limit: {limit}")
    return await repository.get_fused_workflow_spans(service_name, limit)


@router.get("/traces/{trace_id}/spans", response_model=list[dict[str, Any]])
async def get_trace_spans(trace_id: str) -> list[dict[str, Any]]:
    """Get all spans for a specific trace.

    Args:
        trace_id: Trace ID (32-character hex string).

    Returns:
        List of all spans in the trace, ordered by start time (most recent first).

    Example:
        GET /api/v1/observability/traces/0123456789abcdef0123456789abcdef/spans
    """
    logger.debug(f"Fetching spans for trace: {trace_id}")
    return await repository.get_fused_trace_spans(trace_id)


@router.get("/traces/{trace_id}/spans/{span_id}", response_model=dict[str, Any] | None)
async def get_span(trace_id: str, span_id: str) -> dict[str, Any] | None:
    """Get a specific span by trace ID and span ID.

    Args:
        trace_id: Trace ID (32-character hex string).
        span_id: Span ID (16-character hex string).

    Returns:
        Span object if found, None otherwise.

    Example:
        GET /api/v1/observability/traces/0123...abcdef/spans/0123456789abcdef
    """
    logger.debug(f"Fetching span: trace_id={trace_id}, span_id={span_id}")
    span = await repository.get_fused_span(trace_id, span_id)

    if span is None:
        logger.warning(f"Span not found: trace_id={trace_id}, span_id={span_id}")
        return None

    return span
