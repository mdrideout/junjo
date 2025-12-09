"""Repository for querying OTEL spans from V4 architecture with unified WAL fusion.

V4 Unified Fusion Flow:
1. Query DuckDB metadata (span_metadata, services, parquet_files) for filtering
2. Get WAL data as Arrow IPC via gRPC
3. Use UnifiedSpanQuery to merge WAL + Parquet in a single DataFusion query
4. Deduplication handled by SQL (Parquet wins if same span_id exists)

This module provides data access methods for span query endpoints.
Functions with "_fused" suffix query both Parquet and WAL via unified queries.
"""

import grpc
import pyarrow as pa
from loguru import logger

from app.db_duckdb import v4_repository
from app.db_duckdb.unified_query import UnifiedSpanQuery
from app.features.span_ingestion.ingestion_client import IngestionClient

# Module-level WAL client for reuse
_wal_client: IngestionClient | None = None


async def _get_wal_client() -> IngestionClient:
    """Get or create the WAL query client.

    Returns a connected client ready for queries.
    The client is cached at module level for reuse.
    """
    global _wal_client
    if _wal_client is None:
        _wal_client = IngestionClient()
        await _wal_client.connect()
    return _wal_client


async def _reset_wal_client() -> None:
    """Reset the WAL client after an error.

    This closes the existing client and clears the cache so the next
    call to _get_wal_client() will create a fresh connection.
    """
    global _wal_client
    if _wal_client is not None:
        try:
            await _wal_client.close()
        except Exception:
            pass  # Ignore close errors
        _wal_client = None


async def _get_wal_spans_arrow(
    *,
    trace_id: str | None = None,
    service_name: str | None = None,
    root_only: bool = False,
    workflow_only: bool = False,
    limit: int = 0,
) -> pa.Table:
    """Get WAL spans as Arrow Table.

    Returns empty table if WAL query fails (graceful degradation).
    """
    try:
        client = await _get_wal_client()
        return await client.get_wal_spans_arrow(
            trace_id=trace_id,
            service_name=service_name,
            root_only=root_only,
            workflow_only=workflow_only,
            limit=limit,
        )
    except grpc.aio.AioRpcError as e:
        logger.warning(
            "WAL Arrow query failed, returning empty table",
            extra={
                "trace_id": trace_id,
                "service_name": service_name,
                "code": str(e.code()),
                "details": e.details(),
            },
        )
        await _reset_wal_client()
        return pa.table({})
    except Exception as e:
        logger.warning(
            "WAL client error, returning empty table",
            extra={
                "trace_id": trace_id,
                "service_name": service_name,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        await _reset_wal_client()
        return pa.table({})


async def _get_wal_distinct_service_names() -> list[str]:
    """Query distinct service names from WAL.

    Returns empty list if WAL query fails (graceful degradation).
    """
    try:
        client = await _get_wal_client()
        return await client.get_wal_distinct_service_names()
    except grpc.aio.AioRpcError as e:
        logger.warning(
            "WAL service names query failed, returning empty list",
            extra={"code": str(e.code()), "details": e.details()},
        )
        await _reset_wal_client()
        return []
    except Exception as e:
        logger.warning(
            "WAL client error, returning empty list",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        await _reset_wal_client()
        return []


def _merge_service_names(parquet_services: list[str], wal_services: list[str]) -> list[str]:
    """Merge service names from Parquet and WAL.

    Args:
        parquet_services: Services from DuckDB metadata
        wal_services: Services from WAL

    Returns:
        Sorted unique list of service names
    """
    return sorted(set(parquet_services) | set(wal_services))


async def get_fused_distinct_service_names() -> list[str]:
    """Get list of all distinct service names from Parquet and WAL.

    Fusion query:
    1. Query DuckDB services table (Parquet-indexed)
    2. Query WAL for service names not yet flushed
    3. Merge and deduplicate

    Returns:
        List of service names in alphabetical order.
    """
    parquet_services = v4_repository.get_parquet_services()
    wal_services = await _get_wal_distinct_service_names()

    merged = _merge_service_names(parquet_services, wal_services)

    logger.debug(
        "Merged service names",
        extra={
            "parquet_count": len(parquet_services),
            "wal_count": len(wal_services),
            "merged_count": len(merged),
        },
    )

    return merged


async def get_fused_service_spans(service_name: str, limit: int = 500) -> list[dict]:
    """Get all spans for a service from Parquet and WAL.

    Uses unified DataFusion query for Parquet + WAL fusion.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of span dictionaries with full attributes.
    """
    # Get file paths from metadata
    file_paths = v4_repository.get_file_paths_for_service(service_name, limit=limit)

    # Get WAL spans as Arrow
    wal_table = await _get_wal_spans_arrow(service_name=service_name, limit=limit)

    # Use unified query for fusion
    query = UnifiedSpanQuery()
    query.register_parquet(file_paths)
    query.register_wal(wal_table)

    results = query.query_spans(service_name=service_name, limit=limit)

    logger.debug(
        "Unified service spans query",
        extra={
            "service_name": service_name,
            "file_count": len(file_paths),
            "wal_rows": wal_table.num_rows,
            "result_count": len(results),
        },
    )

    return results


async def get_fused_root_spans(service_name: str, limit: int = 500) -> list[dict]:
    """Get root spans (no parent) for a service from Parquet and WAL.

    Uses unified DataFusion query with root_only filter.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of root span dictionaries, sorted by start_time DESC.
    """
    # Get file paths for root spans
    file_paths = v4_repository.get_file_paths_for_service(service_name, limit=limit, is_root=True)

    # Get WAL root spans as Arrow
    wal_table = await _get_wal_spans_arrow(service_name=service_name, root_only=True, limit=limit)

    # Use unified query for fusion
    query = UnifiedSpanQuery()
    query.register_parquet(file_paths)
    query.register_wal(wal_table)

    results = query.query_spans(service_name=service_name, root_only=True, limit=limit)

    logger.debug(
        "Unified root spans query",
        extra={
            "service_name": service_name,
            "file_count": len(file_paths),
            "wal_rows": wal_table.num_rows,
            "result_count": len(results),
        },
    )

    return results


async def get_fused_root_spans_with_llm(service_name: str, limit: int = 500) -> list[dict]:
    """Get root spans that are part of traces containing LLM operations.

    This is a more complex query that requires:
    1. Get LLM trace IDs from metadata
    2. Query root spans and filter to LLM traces

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of root span dictionaries from LLM traces.
    """
    # Step 1: Get Parquet LLM trace IDs (indexed lookup - fast)
    parquet_llm_trace_ids = set(v4_repository.get_llm_trace_ids(service_name, limit * 2))

    # Step 2: Get all root spans (both Parquet and WAL)
    all_root_spans = await get_fused_root_spans(service_name, limit * 2)

    # Step 3: Filter to LLM traces
    # For Parquet spans, use the indexed lookup
    # For WAL spans, we need to check the trace
    llm_root_spans = []

    for span in all_root_spans:
        trace_id = span.get("trace_id")
        if trace_id in parquet_llm_trace_ids:
            llm_root_spans.append(span)
        else:
            # Check if this trace has LLM spans in WAL
            # This is expensive but necessary for unflushed traces
            trace_spans = await get_fused_trace_spans(trace_id)
            for ts in trace_spans:
                attrs = ts.get("attributes_json", {})
                if attrs.get("openinference.span.kind") == "LLM":
                    llm_root_spans.append(span)
                    break

        if len(llm_root_spans) >= limit:
            break

    logger.debug(
        "Unified LLM root spans query",
        extra={
            "service_name": service_name,
            "parquet_llm_trace_count": len(parquet_llm_trace_ids),
            "result_count": len(llm_root_spans),
        },
    )

    return llm_root_spans[:limit]


async def get_fused_workflow_spans(service_name: str, limit: int = 500) -> list[dict]:
    """Get workflow-type spans for a service from Parquet and WAL.

    Uses unified DataFusion query with workflow_only filter.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of workflow span dictionaries.
    """
    # Get file paths containing workflow spans (metadata-indexed)
    file_paths = v4_repository.get_file_paths_for_junjo_type(service_name, "workflow", limit=limit)

    # Get WAL workflow spans as Arrow
    wal_table = await _get_wal_spans_arrow(
        service_name=service_name, workflow_only=True, limit=limit
    )

    # Use unified query for fusion
    query = UnifiedSpanQuery()
    query.register_parquet(file_paths)
    query.register_wal(wal_table)

    results = query.query_spans(service_name=service_name, workflow_only=True, limit=limit)

    logger.debug(
        "Unified workflow spans query",
        extra={
            "service_name": service_name,
            "file_count": len(file_paths),
            "wal_rows": wal_table.num_rows,
            "result_count": len(results),
        },
    )

    return results


async def get_fused_trace_spans(trace_id: str) -> list[dict]:
    """Get all spans for a specific trace from Parquet and WAL.

    Uses unified DataFusion query filtering by trace_id.

    Args:
        trace_id: Trace ID (32-char hex string).

    Returns:
        List of span dictionaries ordered by start time DESC.
    """
    # Get file paths for this trace
    file_paths = v4_repository.get_file_paths_for_trace(trace_id)

    # Get WAL spans for this trace as Arrow
    wal_table = await _get_wal_spans_arrow(trace_id=trace_id)

    # Use unified query for fusion
    query = UnifiedSpanQuery()
    query.register_parquet(file_paths)
    query.register_wal(wal_table)

    results = query.query_spans(trace_id=trace_id)

    logger.debug(
        "Unified trace spans query",
        extra={
            "trace_id": trace_id,
            "file_count": len(file_paths),
            "wal_rows": wal_table.num_rows,
            "result_count": len(results),
        },
    )

    return results


async def get_fused_span(trace_id: str, span_id: str) -> dict | None:
    """Get a specific span by trace ID and span ID from Parquet or WAL.

    Uses unified DataFusion query and filters to specific span.

    Args:
        trace_id: Trace ID (32-char hex string).
        span_id: Span ID (16-char hex string).

    Returns:
        Span dictionary if found, None otherwise.
    """
    # Get all spans for the trace and filter to the specific span
    trace_spans = await get_fused_trace_spans(trace_id)

    for span in trace_spans:
        if span.get("span_id") == span_id:
            return span

    logger.debug(f"Span not found: {span_id}")
    return None
