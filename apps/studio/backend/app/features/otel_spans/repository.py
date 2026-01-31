"""Repository for querying OTEL spans from V4 two-tier architecture.

Two-Tier Architecture (Rust Ingestion):
- COLD: Parquet files from WAL flushes (indexed in SQLite metadata)
- HOT: On-demand Parquet snapshot (backend reads file directly)

Query Flow:
1. Query SQLite metadata for COLD tier file paths
2. Call PrepareHotSnapshot RPC to get hot snapshot path
3. Register COLD and HOT in DataFusion
4. Query with deduplication COLD > HOT

Deduplication priority: COLD > HOT (same (trace_id, span_id)).

This module provides data access methods for span query endpoints.
Functions with "_fused" suffix query both tiers via unified queries.

Memory-Optimized Architecture:
- SQLite metadata index: 15-30 MB (hundreds of MB avoided vs per-span indexing)
- Per-trace indexing instead of per-span
- DataFusion handles Parquet queries
"""

import grpc
from loguru import logger

from app.db_sqlite.metadata import repository as metadata_repo
from app.features.otel_spans.datafusion_query import UnifiedSpanQuery
from app.features.span_ingestion.ingestion_client import IngestionClient

# Module-level ingestion client for reuse
_ingestion_client: IngestionClient | None = None

# Upper bound on how many cold Parquet files we register for service-scoped queries.
# This prevents DataFusion from loading an
# unbounded number of files into memory.
MAX_COLD_FILES_PER_SERVICE_QUERY = 20
MAX_RECENT_COLD_FILES_PER_QUERY = 20
MAX_RECENT_COLD_FILES_FOR_SERVICE_DISCOVERY = 5


def _augment_with_recent_cold_files(
    file_paths: list[str],
    recent_cold_paths: list[str],
    *,
    limit: int,
) -> list[str]:
    """Prepend a bounded list of "recent cold" files (ingestion is source of truth)."""
    recent = recent_cold_paths[: max(limit, 0)]
    if not recent:
        return file_paths

    recent_set = set(recent)
    return [*recent, *[p for p in file_paths if p not in recent_set]]


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


async def _get_ingestion_query_context() -> tuple[str | None, list[str]]:
    """Get hot snapshot path and recent cold files from ingestion service.

    Calls PrepareHotSnapshot RPC to create a stable Parquet snapshot.
    Returns (None, []) if the operation fails (graceful degradation to COLD-only).
    """
    try:
        client = await _get_ingestion_client()
        result = await client.prepare_hot_snapshot()

        recent_cold_paths = result.recent_cold_paths

        # success=true can still mean "no data" (empty WAL) where snapshot_path is empty.
        if result.success and result.snapshot_path and result.row_count > 0:
            logger.debug(
                "Hot snapshot ready",
                extra={
                    "path": result.snapshot_path,
                    "row_count": result.row_count,
                    "size_bytes": result.file_size_bytes,
                    "recent_cold_paths": len(recent_cold_paths),
                },
            )
            return result.snapshot_path, recent_cold_paths

        if result.success:
            logger.debug(
                "Hot snapshot is empty (no unflushed spans)",
                extra={
                    "row_count": result.row_count,
                    "size_bytes": result.file_size_bytes,
                    "recent_cold_paths": len(recent_cold_paths),
                },
            )
            return None, recent_cold_paths

        logger.warning(
            "Hot snapshot preparation failed",
            extra={"error": result.error_message},
        )
        return None, recent_cold_paths

    except grpc.aio.AioRpcError as e:
        logger.warning(
            "PrepareHotSnapshot RPC failed, will use COLD only",
            extra={"code": str(e.code()), "details": e.details()},
        )
        await _reset_ingestion_client()
        return None, []
    except Exception as e:
        logger.warning(
            "PrepareHotSnapshot error, will use COLD only",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        await _reset_ingestion_client()
        return None, []


async def get_fused_distinct_service_names() -> list[str]:
    """Get list of all distinct service names from both tiers.

    Two-tier query:
    1. Query COLD service names from SQLite metadata (instant)
    2. Get HOT tier snapshot path from gRPC
    3. Query distinct service names from HOT snapshot only
    4. UNION the two sets in Python

    Returns:
        List of service names in alphabetical order.
    """
    # COLD: SQLite metadata already contains distinct services
    cold_services = metadata_repo.get_services()

    # Get ingestion query context once for this request.
    hot_snapshot_path, recent_cold_paths = await _get_ingestion_query_context()

    # RECENT COLD: include newly flushed (but not yet indexed) Parquet files.
    recent_services: list[str] = []
    recent_files = recent_cold_paths[:MAX_RECENT_COLD_FILES_FOR_SERVICE_DISCOVERY]
    if recent_files:
        recent_query = UnifiedSpanQuery()
        recent_query.register_cold(recent_files)
        recent_services = recent_query.query_distinct_service_names()

    # HOT: Query distinct services from the hot snapshot only (small file)
    hot_services: list[str] = []
    if hot_snapshot_path:
        query = UnifiedSpanQuery()
        query.register_hot(hot_snapshot_path)
        hot_services = query.query_distinct_service_names()

    services = sorted(set(cold_services) | set(recent_services) | set(hot_services))

    logger.debug(
        "Two-tier service names query",
        extra={
            "cold_service_count": len(cold_services),
            "recent_file_count": len(recent_files),
            "recent_service_count": len(recent_services),
            "hot_snapshot": hot_snapshot_path is not None,
            "hot_service_count": len(hot_services),
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
    hot_snapshot_path, recent_cold_paths = await _get_ingestion_query_context()

    # Get cold tier file paths from SQLite metadata
    cold_file_paths = metadata_repo.get_file_paths_for_service(
        service_name,
        limit=MAX_COLD_FILES_PER_SERVICE_QUERY,
    )
    cold_file_paths = _augment_with_recent_cold_files(
        cold_file_paths,
        recent_cold_paths,
        limit=MAX_RECENT_COLD_FILES_PER_QUERY,
    )

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
    hot_snapshot_path, recent_cold_paths = await _get_ingestion_query_context()

    # Get cold tier file paths for the service
    # SQLite doesn't filter by is_root; DataFusion filters for parent_span_id IS NULL
    cold_file_paths = metadata_repo.get_file_paths_for_service(
        service_name,
        limit=MAX_COLD_FILES_PER_SERVICE_QUERY,
    )
    cold_file_paths = _augment_with_recent_cold_files(
        cold_file_paths,
        recent_cold_paths,
        limit=MAX_RECENT_COLD_FILES_PER_QUERY,
    )

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
    # Prepare ingestion query context once and reuse throughout this request.
    hot_snapshot_path, recent_cold_paths = await _get_ingestion_query_context()

    # Query a bounded window of recent root spans across both tiers.
    cold_file_paths = metadata_repo.get_file_paths_for_service(
        service_name,
        limit=MAX_COLD_FILES_PER_SERVICE_QUERY,
    )
    cold_file_paths = _augment_with_recent_cold_files(
        cold_file_paths,
        recent_cold_paths,
        limit=MAX_RECENT_COLD_FILES_PER_QUERY,
    )

    candidate_limit = min(limit * 5, 5000)
    query = UnifiedSpanQuery()
    query.register_cold(cold_file_paths)
    query.register_hot(hot_snapshot_path)
    candidate_root_spans = query.query_spans_two_tier(
        service_name=service_name,
        root_only=True,
        limit=candidate_limit,
    )

    candidate_trace_ids = {
        span.get("trace_id") for span in candidate_root_spans if span.get("trace_id")
    }

    # COLD: Use SQLite llm_traces table to filter the candidate trace IDs.
    cold_llm_trace_ids = metadata_repo.filter_llm_trace_ids(service_name, candidate_trace_ids)

    # HOT: Scan only the hot snapshot to find traces with LLM spans not yet indexed.
    hot_llm_trace_ids: set[str] = set()
    if hot_snapshot_path and candidate_trace_ids:
        hot_query = UnifiedSpanQuery()
        hot_query.register_hot(hot_snapshot_path)
        hot_spans = hot_query.query_spans_two_tier(service_name=service_name)
        for span in hot_spans:
            trace_id = span.get("trace_id")
            if not trace_id or trace_id not in candidate_trace_ids:
                continue
            attrs = span.get("attributes_json", {})
            if attrs.get("openinference.span.kind") == "LLM":
                hot_llm_trace_ids.add(trace_id)

    llm_trace_ids = cold_llm_trace_ids | hot_llm_trace_ids
    llm_root_spans = [s for s in candidate_root_spans if s.get("trace_id") in llm_trace_ids]

    logger.debug(
        "Two-tier LLM root spans query",
        extra={
            "service_name": service_name,
            "candidate_root_span_count": len(candidate_root_spans),
            "cold_llm_trace_count": len(cold_llm_trace_ids),
            "hot_llm_trace_count": len(hot_llm_trace_ids),
            "result_count": len(llm_root_spans[:limit]),
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
    hot_snapshot_path, recent_cold_paths = await _get_ingestion_query_context()

    # Get cold tier file paths containing workflow spans from SQLite
    cold_file_paths = metadata_repo.get_workflow_file_paths(
        service_name,
        limit=MAX_COLD_FILES_PER_SERVICE_QUERY,
    )
    cold_file_paths = _augment_with_recent_cold_files(
        cold_file_paths,
        recent_cold_paths,
        limit=MAX_RECENT_COLD_FILES_PER_QUERY,
    )

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
    hot_snapshot_path, recent_cold_paths = await _get_ingestion_query_context()

    # Get cold tier file paths for this trace from SQLite
    cold_file_paths = metadata_repo.get_file_paths_for_trace(trace_id)
    cold_file_paths = _augment_with_recent_cold_files(
        cold_file_paths,
        recent_cold_paths,
        limit=MAX_RECENT_COLD_FILES_PER_QUERY,
    )

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
