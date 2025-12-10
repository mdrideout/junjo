"""Repository for querying OTEL spans from V4 three-tier architecture.

Three-Tier Architecture:
- COLD: Parquet files from full WAL flushes (indexed in DuckDB)
- WARM: Incremental parquet snapshots in tmp/ (globbed, not indexed)
- HOT: Live SQLite data since last warm snapshot (gRPC Arrow IPC)

Query Flow:
1. Query DuckDB metadata (span_metadata, services, parquet_files) for COLD tier paths
2. Get warm cursor from ingestion service (last warm ULID)
3. Get HOT tier data as Arrow IPC via gRPC (only spans since last warm snapshot)
4. Register all three tiers in DataFusion and query with deduplication

Deduplication priority: COLD > WARM > HOT (same span_id).

This module provides data access methods for span query endpoints.
Functions with "_fused" suffix query all three tiers via unified queries.
"""

import grpc
import pyarrow as pa
from loguru import logger

from app.db_duckdb import v4_repository
from app.db_duckdb.unified_query import UnifiedSpanQuery
from app.features.span_ingestion.ingestion_client import IngestionClient, WarmCursor

# Module-level ingestion client for reuse
_ingestion_client: IngestionClient | None = None


async def _get_ingestion_client() -> IngestionClient:
    """Get or create the ingestion gRPC client.

    Returns a connected client ready for queries.
    The client is cached at module level for reuse.
    """
    global _ingestion_client
    if _ingestion_client is None:
        _ingestion_client = IngestionClient()
        await _ingestion_client.connect()
    return _ingestion_client


async def _reset_ingestion_client() -> None:
    """Reset the ingestion client after an error.

    This closes the existing client and clears the cache so the next
    call to _get_ingestion_client() will create a fresh connection.
    """
    global _ingestion_client
    if _ingestion_client is not None:
        try:
            await _ingestion_client.close()
        except Exception:
            pass  # Ignore close errors
        _ingestion_client = None


# ===========================================================================
# Three-Tier Data Access Helpers
# ===========================================================================


async def _get_warm_cursor() -> WarmCursor | None:
    """Get the warm snapshot cursor from ingestion service.

    Returns the cursor state indicating what's in warm tier vs hot tier.
    Returns None if the query fails (graceful degradation to full WAL query).
    """
    try:
        client = await _get_ingestion_client()
        return await client.get_warm_cursor()
    except grpc.aio.AioRpcError as e:
        logger.warning(
            "Warm cursor query failed, will use full WAL",
            extra={"code": str(e.code()), "details": e.details()},
        )
        await _reset_ingestion_client()
        return None
    except Exception as e:
        logger.warning(
            "Warm cursor error, will use full WAL",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        await _reset_ingestion_client()
        return None


async def _get_hot_spans_arrow(
    *,
    since_warm_ulid: bytes | None = None,
    trace_id: str | None = None,
    service_name: str | None = None,
    root_only: bool = False,
    workflow_only: bool = False,
    limit: int = 0,
) -> pa.Table:
    """Get HOT tier spans (since last warm snapshot) as Arrow Table.

    This returns only the newest data that hasn't been snapshotted to warm.
    Returns empty table if query fails (graceful degradation).

    Args:
        since_warm_ulid: Only return spans newer than this ULID
        trace_id: Filter by trace ID
        service_name: Filter by service name
        root_only: Only return root spans
        workflow_only: Only return workflow spans
        limit: Maximum rows (0 = no limit)

    Returns:
        PyArrow Table with hot tier spans
    """
    try:
        client = await _get_ingestion_client()
        return await client.get_hot_spans_arrow(
            since_warm_ulid=since_warm_ulid,
            trace_id=trace_id,
            service_name=service_name,
            root_only=root_only,
            workflow_only=workflow_only,
            limit=limit,
        )
    except grpc.aio.AioRpcError as e:
        logger.warning(
            "HOT tier query failed, returning empty table",
            extra={
                "trace_id": trace_id,
                "service_name": service_name,
                "code": str(e.code()),
                "details": e.details(),
            },
        )
        await _reset_ingestion_client()
        return pa.table({})
    except Exception as e:
        logger.warning(
            "HOT tier client error, returning empty table",
            extra={
                "trace_id": trace_id,
                "service_name": service_name,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        await _reset_ingestion_client()
        return pa.table({})


async def _get_wal_spans_arrow(
    *,
    trace_id: str | None = None,
    service_name: str | None = None,
    root_only: bool = False,
    workflow_only: bool = False,
    limit: int = 0,
) -> pa.Table:
    """Get ALL WAL spans as Arrow Table (legacy, full WAL query).

    DEPRECATED: Use _get_hot_spans_arrow for three-tier queries.
    This remains for fallback when warm cursor is unavailable.

    Returns empty table if WAL query fails (graceful degradation).
    """
    try:
        client = await _get_ingestion_client()
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
        await _reset_ingestion_client()
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
        await _reset_ingestion_client()
        return pa.table({})


async def get_fused_distinct_service_names() -> list[str]:
    """Get list of all distinct service names from all three tiers.

    Three-tier query:
    1. Register COLD tier (Parquet from DuckDB metadata)
    2. Register WARM tier (glob tmp/*.parquet)
    3. Get HOT tier from gRPC
    4. Query distinct service names via DataFusion UNION

    Returns:
        List of service names in alphabetical order.
    """
    # Get cold tier file paths (all parquet files, no filter)
    cold_file_paths = v4_repository.get_all_parquet_file_paths()

    # Get warm cursor and hot data
    warm_cursor = await _get_warm_cursor()
    since_warm_ulid = warm_cursor.last_warm_ulid if warm_cursor else None

    # Get hot tier data
    hot_table = await _get_hot_spans_arrow(since_warm_ulid=since_warm_ulid)

    # Create unified query with three tiers
    query = UnifiedSpanQuery()
    query.register_cold(cold_file_paths)
    warm_files = query.register_warm()
    query.register_hot(hot_table)

    # Query distinct service names across all tiers
    services = query.query_distinct_service_names()

    logger.debug(
        "Three-tier service names query",
        extra={
            "cold_files": len(cold_file_paths),
            "warm_files": len(warm_files),
            "hot_rows": hot_table.num_rows if hot_table.num_columns > 0 else 0,
            "service_count": len(services),
        },
    )

    return services


async def get_fused_service_spans(service_name: str, limit: int = 500) -> list[dict]:
    """Get all spans for a service from all three tiers.

    Uses three-tier DataFusion query: Cold + Warm + Hot.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of span dictionaries with full attributes.
    """
    # Get cold tier file paths from metadata
    cold_file_paths = v4_repository.get_file_paths_for_service(service_name, limit=limit)

    # Get warm cursor and hot data
    warm_cursor = await _get_warm_cursor()
    since_warm_ulid = warm_cursor.last_warm_ulid if warm_cursor else None

    # Get hot tier spans
    hot_table = await _get_hot_spans_arrow(
        since_warm_ulid=since_warm_ulid, service_name=service_name, limit=limit
    )

    # Use three-tier unified query
    query = UnifiedSpanQuery()
    query.register_cold(cold_file_paths)
    warm_files = query.register_warm()
    query.register_hot(hot_table)

    results = query.query_spans_three_tier(service_name=service_name, limit=limit)

    logger.debug(
        "Three-tier service spans query",
        extra={
            "service_name": service_name,
            "cold_files": len(cold_file_paths),
            "warm_files": len(warm_files),
            "hot_rows": hot_table.num_rows if hot_table.num_columns > 0 else 0,
            "result_count": len(results),
        },
    )

    return results


async def get_fused_root_spans(service_name: str, limit: int = 500) -> list[dict]:
    """Get root spans (no parent) for a service from all three tiers.

    Uses three-tier DataFusion query with root_only filter.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of root span dictionaries, sorted by start_time DESC.
    """
    # Get cold tier file paths for root spans
    cold_file_paths = v4_repository.get_file_paths_for_service(
        service_name, limit=limit, is_root=True
    )

    # Get warm cursor and hot data
    warm_cursor = await _get_warm_cursor()
    since_warm_ulid = warm_cursor.last_warm_ulid if warm_cursor else None

    # Get hot tier root spans
    hot_table = await _get_hot_spans_arrow(
        since_warm_ulid=since_warm_ulid, service_name=service_name, root_only=True, limit=limit
    )

    # Use three-tier unified query
    query = UnifiedSpanQuery()
    query.register_cold(cold_file_paths)
    warm_files = query.register_warm()
    query.register_hot(hot_table)

    results = query.query_spans_three_tier(service_name=service_name, root_only=True, limit=limit)

    logger.debug(
        "Three-tier root spans query",
        extra={
            "service_name": service_name,
            "cold_files": len(cold_file_paths),
            "warm_files": len(warm_files),
            "hot_rows": hot_table.num_rows if hot_table.num_columns > 0 else 0,
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
    """Get workflow-type spans for a service from all three tiers.

    Uses three-tier DataFusion query with workflow_only filter.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of workflow span dictionaries.
    """
    # Get cold tier file paths containing workflow spans (metadata-indexed)
    cold_file_paths = v4_repository.get_file_paths_for_junjo_type(
        service_name, "workflow", limit=limit
    )

    # Get warm cursor and hot data
    warm_cursor = await _get_warm_cursor()
    since_warm_ulid = warm_cursor.last_warm_ulid if warm_cursor else None

    # Get hot tier workflow spans
    hot_table = await _get_hot_spans_arrow(
        since_warm_ulid=since_warm_ulid, service_name=service_name, workflow_only=True, limit=limit
    )

    # Use three-tier unified query
    query = UnifiedSpanQuery()
    query.register_cold(cold_file_paths)
    warm_files = query.register_warm()
    query.register_hot(hot_table)

    results = query.query_spans_three_tier(
        service_name=service_name, workflow_only=True, limit=limit
    )

    logger.debug(
        "Three-tier workflow spans query",
        extra={
            "service_name": service_name,
            "cold_files": len(cold_file_paths),
            "warm_files": len(warm_files),
            "hot_rows": hot_table.num_rows if hot_table.num_columns > 0 else 0,
            "result_count": len(results),
        },
    )

    return results


async def get_fused_trace_spans(trace_id: str) -> list[dict]:
    """Get all spans for a specific trace from all three tiers.

    Uses three-tier DataFusion query filtering by trace_id.

    Args:
        trace_id: Trace ID (32-char hex string).

    Returns:
        List of span dictionaries ordered by start time DESC.
    """
    # Get cold tier file paths for this trace
    cold_file_paths = v4_repository.get_file_paths_for_trace(trace_id)

    # Get warm cursor and hot data
    warm_cursor = await _get_warm_cursor()
    since_warm_ulid = warm_cursor.last_warm_ulid if warm_cursor else None

    # Get hot tier spans for this trace
    hot_table = await _get_hot_spans_arrow(since_warm_ulid=since_warm_ulid, trace_id=trace_id)

    # Use three-tier unified query
    query = UnifiedSpanQuery()
    query.register_cold(cold_file_paths)
    warm_files = query.register_warm()
    query.register_hot(hot_table)

    results = query.query_spans_three_tier(trace_id=trace_id)

    logger.debug(
        "Three-tier trace spans query",
        extra={
            "trace_id": trace_id,
            "cold_files": len(cold_file_paths),
            "warm_files": len(warm_files),
            "hot_rows": hot_table.num_rows if hot_table.num_columns > 0 else 0,
            "result_count": len(results),
        },
    )

    return results


async def get_fused_span(trace_id: str, span_id: str) -> dict | None:
    """Get a specific span by trace ID and span ID from all three tiers.

    Uses three-tier query and filters to specific span.

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
