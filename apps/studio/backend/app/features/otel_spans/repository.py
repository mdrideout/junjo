"""Repository for querying OTEL spans from V4 two-tier architecture.

Two-Tier Architecture (Rust Ingestion):
- COLD: Parquet files from WAL flushes (indexed in SQLite metadata)
- HOT: On-demand Parquet snapshot (backend reads file directly)

Query Flow:
1. Query SQLite metadata for COLD tier file paths
2. Call PrepareHotSnapshot RPC to get hot snapshot path
3. Register COLD and HOT in DataFusion
4. Query with deduplication COLD > HOT

Deduplication priority: COLD > HOT (same span_id).

This module provides data access methods for span query endpoints.
Functions with "_fused" suffix query both tiers via unified queries.

Memory-Optimized Architecture:
- SQLite metadata index: 15-30 MB (10-20x reduction from DuckDB)
- Per-trace indexing instead of per-span
- DataFusion handles Parquet queries
"""

import grpc
from loguru import logger

from app.db_duckdb.unified_query import UnifiedSpanQuery
from app.db_sqlite.metadata import repository as metadata_repo
from app.features.span_ingestion.ingestion_client import IngestionClient

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
# Two-Tier Data Access Helpers
# ===========================================================================


async def _get_hot_snapshot_path() -> str | None:
    """Get the hot snapshot file path from ingestion service.

    Calls PrepareHotSnapshot RPC to create a stable Parquet snapshot.
    Returns None if the operation fails (graceful degradation to COLD-only).
    """
    try:
        client = await _get_ingestion_client()
        result = await client.prepare_hot_snapshot()

        if result.success and result.snapshot_path:
            logger.debug(
                "Hot snapshot ready",
                extra={
                    "path": result.snapshot_path,
                    "row_count": result.row_count,
                    "size_bytes": result.file_size_bytes,
                },
            )
            return result.snapshot_path
        else:
            logger.warning(
                "Hot snapshot preparation failed",
                extra={"error": result.error_message},
            )
            return None

    except grpc.aio.AioRpcError as e:
        logger.warning(
            "Hot snapshot RPC failed, will use COLD only",
            extra={"code": str(e.code()), "details": e.details()},
        )
        await _reset_ingestion_client()
        return None
    except Exception as e:
        logger.warning(
            "Hot snapshot error, will use COLD only",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        await _reset_ingestion_client()
        return None


async def get_fused_distinct_service_names() -> list[str]:
    """Get list of all distinct service names from both tiers.

    Two-tier query:
    1. Register COLD tier (Parquet from SQLite metadata)
    2. Get HOT tier snapshot path from gRPC
    3. Query distinct service names via DataFusion UNION

    Returns:
        List of service names in alphabetical order.
    """
    # Get cold tier file paths from SQLite metadata
    cold_file_paths = metadata_repo.get_all_parquet_file_paths()

    # Get hot snapshot path
    hot_snapshot_path = await _get_hot_snapshot_path()

    # Create unified query with two tiers
    query = UnifiedSpanQuery()
    query.register_cold(cold_file_paths)
    query.register_hot(hot_snapshot_path)

    # Query distinct service names across all tiers
    services = query.query_distinct_service_names()

    logger.debug(
        "Two-tier service names query",
        extra={
            "cold_files": len(cold_file_paths),
            "hot_snapshot": hot_snapshot_path is not None,
            "service_count": len(services),
        },
    )

    return services


async def get_fused_service_spans(service_name: str, limit: int = 500) -> list[dict]:
    """Get all spans for a service from both tiers.

    Uses two-tier DataFusion query: Cold + Hot.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of span dictionaries with full attributes.
    """
    # Get cold tier file paths from SQLite metadata
    cold_file_paths = metadata_repo.get_file_paths_for_service(service_name, limit=limit)

    # Get hot snapshot path
    hot_snapshot_path = await _get_hot_snapshot_path()

    # Use two-tier unified query
    query = UnifiedSpanQuery()
    query.register_cold(cold_file_paths)
    query.register_hot(hot_snapshot_path)

    results = query.query_spans_two_tier(service_name=service_name, limit=limit)

    logger.debug(
        "Two-tier service spans query",
        extra={
            "service_name": service_name,
            "cold_files": len(cold_file_paths),
            "hot_snapshot": hot_snapshot_path is not None,
            "result_count": len(results),
        },
    )

    return results


async def get_fused_root_spans(service_name: str, limit: int = 500) -> list[dict]:
    """Get root spans (no parent) for a service from both tiers.

    Uses two-tier DataFusion query with root_only filter.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of root span dictionaries, sorted by start_time DESC.
    """
    # Get cold tier file paths for the service
    # SQLite doesn't filter by is_root; DataFusion filters for parent_span_id IS NULL
    cold_file_paths = metadata_repo.get_file_paths_for_service(service_name, limit=limit)

    # Get hot snapshot path
    hot_snapshot_path = await _get_hot_snapshot_path()

    # Use two-tier unified query
    query = UnifiedSpanQuery()
    query.register_cold(cold_file_paths)
    query.register_hot(hot_snapshot_path)

    results = query.query_spans_two_tier(service_name=service_name, root_only=True, limit=limit)

    logger.debug(
        "Two-tier root spans query",
        extra={
            "service_name": service_name,
            "cold_files": len(cold_file_paths),
            "hot_snapshot": hot_snapshot_path is not None,
            "result_count": len(results),
        },
    )

    return results


async def get_fused_root_spans_with_llm(service_name: str, limit: int = 500) -> list[dict]:
    """Get root spans that are part of traces containing LLM operations.

    This is a more complex query that requires:
    1. Get LLM trace IDs from SQLite metadata
    2. Query root spans and filter to LLM traces

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of root span dictionaries from LLM traces.
    """
    # Step 1: Get Parquet LLM trace IDs from SQLite (indexed lookup - fast)
    parquet_llm_trace_ids = metadata_repo.get_llm_trace_ids(service_name, limit * 2)

    # Step 2: Get all root spans (both Parquet and HOT)
    all_root_spans = await get_fused_root_spans(service_name, limit * 2)

    # Step 3: Filter to LLM traces
    # For Parquet spans, use the indexed lookup
    # For HOT spans, we need to check the trace
    llm_root_spans = []

    for span in all_root_spans:
        trace_id = span.get("trace_id")
        if trace_id in parquet_llm_trace_ids:
            llm_root_spans.append(span)
        else:
            # Check if this trace has LLM spans in HOT tier
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
        "Two-tier LLM root spans query",
        extra={
            "service_name": service_name,
            "parquet_llm_trace_count": len(parquet_llm_trace_ids),
            "result_count": len(llm_root_spans),
        },
    )

    return llm_root_spans[:limit]


async def get_fused_workflow_spans(service_name: str, limit: int = 500) -> list[dict]:
    """Get workflow-type spans for a service from both tiers.

    Uses two-tier DataFusion query with workflow_only filter.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of workflow span dictionaries.
    """
    # Get cold tier file paths containing workflow spans from SQLite
    cold_file_paths = metadata_repo.get_workflow_file_paths(service_name, limit=limit)

    # Get hot snapshot path
    hot_snapshot_path = await _get_hot_snapshot_path()

    # Use two-tier unified query
    query = UnifiedSpanQuery()
    query.register_cold(cold_file_paths)
    query.register_hot(hot_snapshot_path)

    results = query.query_spans_two_tier(service_name=service_name, workflow_only=True, limit=limit)

    logger.debug(
        "Two-tier workflow spans query",
        extra={
            "service_name": service_name,
            "cold_files": len(cold_file_paths),
            "hot_snapshot": hot_snapshot_path is not None,
            "result_count": len(results),
        },
    )

    return results


async def get_fused_trace_spans(trace_id: str) -> list[dict]:
    """Get all spans for a specific trace from both tiers.

    Uses two-tier DataFusion query filtering by trace_id.

    Args:
        trace_id: Trace ID (32-char hex string).

    Returns:
        List of span dictionaries ordered by start time DESC.
    """
    # Get cold tier file paths for this trace from SQLite
    cold_file_paths = metadata_repo.get_file_paths_for_trace(trace_id)

    # Get hot snapshot path
    hot_snapshot_path = await _get_hot_snapshot_path()

    # Use two-tier unified query
    query = UnifiedSpanQuery()
    query.register_cold(cold_file_paths)
    query.register_hot(hot_snapshot_path)

    results = query.query_spans_two_tier(trace_id=trace_id)

    logger.debug(
        "Two-tier trace spans query",
        extra={
            "trace_id": trace_id,
            "cold_files": len(cold_file_paths),
            "hot_snapshot": hot_snapshot_path is not None,
            "result_count": len(results),
        },
    )

    return results


async def get_fused_span(trace_id: str, span_id: str) -> dict | None:
    """Get a specific span by trace ID and span ID from both tiers.

    Uses two-tier query and filters to specific span.

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
