"""Repository for querying OTEL spans from V4 architecture with WAL fusion.

V4 Fusion Flow:
1. Query DuckDB metadata (span_metadata, services, parquet_files) for filtering
2. Use DataFusion to fetch full span data from Parquet files
3. Query WAL via gRPC for hot data not yet flushed to Parquet
4. Merge results, deduplicate by span_id (Parquet wins if same span exists in both)
5. Parse/format response to match API contract

This module provides data access methods for span query endpoints.
Functions with "_fused" suffix query both Parquet and WAL, merging results.
"""

import grpc
from loguru import logger

from app.db_duckdb import datafusion_query, v4_repository
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


async def _get_wal_spans_by_trace(trace_id: str) -> list[dict]:
    """Query spans from WAL by trace ID.

    Returns empty list if WAL query fails (graceful degradation).
    """
    try:
        client = await _get_wal_client()
        return await client.get_wal_spans_by_trace_id(trace_id)
    except grpc.aio.AioRpcError as e:
        logger.warning(
            "WAL trace query failed, returning empty list",
            extra={"trace_id": trace_id, "code": str(e.code()), "details": e.details()},
        )
        await _reset_wal_client()
        return []
    except Exception as e:
        logger.warning(
            "WAL client error, returning empty list",
            extra={"trace_id": trace_id, "error": str(e), "error_type": type(e).__name__},
        )
        await _reset_wal_client()
        return []


async def _get_wal_root_spans(service_name: str, limit: int) -> list[dict]:
    """Query root spans from WAL.

    Returns empty list if WAL query fails (graceful degradation).
    """
    try:
        client = await _get_wal_client()
        return await client.get_wal_root_spans(service_name, limit)
    except grpc.aio.AioRpcError as e:
        logger.warning(
            "WAL root spans query failed, returning empty list",
            extra={"service_name": service_name, "code": str(e.code()), "details": e.details()},
        )
        await _reset_wal_client()
        return []
    except Exception as e:
        logger.warning(
            "WAL client error, returning empty list",
            extra={"service_name": service_name, "error": str(e), "error_type": type(e).__name__},
        )
        await _reset_wal_client()
        return []


async def _get_wal_spans_by_service(service_name: str, limit: int) -> list[dict]:
    """Query spans from WAL by service name.

    Returns empty list if WAL query fails (graceful degradation).
    """
    try:
        client = await _get_wal_client()
        return await client.get_wal_spans_by_service(service_name, limit)
    except grpc.aio.AioRpcError as e:
        logger.warning(
            "WAL service spans query failed, returning empty list",
            extra={"service_name": service_name, "code": str(e.code()), "details": e.details()},
        )
        await _reset_wal_client()
        return []
    except Exception as e:
        logger.warning(
            "WAL client error, returning empty list",
            extra={"service_name": service_name, "error": str(e), "error_type": type(e).__name__},
        )
        await _reset_wal_client()
        return []


async def _get_wal_workflow_spans(service_name: str, limit: int) -> list[dict]:
    """Query workflow spans from WAL.

    Returns empty list if WAL query fails (graceful degradation).
    """
    try:
        client = await _get_wal_client()
        return await client.get_wal_workflow_spans(service_name, limit)
    except grpc.aio.AioRpcError as e:
        logger.warning(
            "WAL workflow spans query failed, returning empty list",
            extra={"service_name": service_name, "code": str(e.code()), "details": e.details()},
        )
        await _reset_wal_client()
        return []
    except Exception as e:
        logger.warning(
            "WAL client error, returning empty list",
            extra={"service_name": service_name, "error": str(e), "error_type": type(e).__name__},
        )
        await _reset_wal_client()
        return []


def _merge_spans(parquet_spans: list[dict], wal_spans: list[dict]) -> list[dict]:
    """Merge spans from Parquet and WAL, deduplicating by span_id.

    Parquet wins if the same span exists in both sources (it's the source of truth
    once flushed).

    Args:
        parquet_spans: Spans from Parquet files
        wal_spans: Spans from WAL

    Returns:
        Merged list of spans, sorted by start_time DESC
    """
    # Build set of span IDs from Parquet (source of truth)
    parquet_span_ids = {span["span_id"] for span in parquet_spans}

    # Start with all Parquet spans
    merged = list(parquet_spans)

    # Add WAL spans that aren't in Parquet
    for span in wal_spans:
        if span["span_id"] not in parquet_span_ids:
            merged.append(span)

    # Sort by start_time DESC (most recent first)
    merged.sort(key=lambda x: x.get("start_time", ""), reverse=True)

    return merged


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
    parquet_services = v4_repository.get_all_services()
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

    Fusion query:
    1. Get Parquet file paths for this service from DuckDB
    2. Query Parquet files via DataFusion for full span data
    3. Query WAL for spans not yet flushed
    4. Merge and deduplicate by span_id

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of span dictionaries with full attributes.
    """
    # Get file paths from metadata
    file_paths = v4_repository.get_file_paths_for_service(service_name, limit=limit)

    # Query Parquet files via DataFusion
    parquet_spans = []
    if file_paths:
        parquet_spans = datafusion_query.get_service_spans(service_name, file_paths, limit=limit)

    # Query WAL for service spans
    wal_spans = await _get_wal_spans_by_service(service_name, limit)

    # Merge results
    merged = _merge_spans(parquet_spans, wal_spans)

    logger.debug(
        "Merged service spans",
        extra={
            "service_name": service_name,
            "parquet_count": len(parquet_spans),
            "wal_count": len(wal_spans),
            "merged_count": len(merged),
        },
    )

    return merged[:limit]


async def get_fused_root_spans(service_name: str, limit: int = 500) -> list[dict]:
    """Get root spans (no parent) for a service from Parquet and WAL.

    Fusion query:
    1. Get file paths that contain root spans for this service
    2. Query Parquet files filtering for root spans
    3. Query WAL for root spans
    4. Merge and deduplicate

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of root span dictionaries, sorted by start_time DESC.
    """
    # Get file paths for root spans
    file_paths = v4_repository.get_file_paths_for_service(service_name, limit=limit, is_root=True)

    # Query Parquet for root spans
    parquet_spans = []
    if file_paths:
        parquet_spans = datafusion_query.get_root_spans(service_name, file_paths, limit=limit)

    # Query WAL for root spans
    wal_spans = await _get_wal_root_spans(service_name, limit)

    # Merge results
    merged = _merge_spans(parquet_spans, wal_spans)

    logger.debug(
        "Merged root spans",
        extra={
            "service_name": service_name,
            "parquet_count": len(parquet_spans),
            "wal_count": len(wal_spans),
            "merged_count": len(merged),
        },
    )

    return merged[:limit]


async def get_fused_root_spans_with_llm(service_name: str, limit: int = 500) -> list[dict]:
    """Get root spans that are part of traces containing LLM operations.

    Fusion query:
    1. Query Parquet for LLM trace IDs (indexed lookup)
    2. Query Parquet for root spans in those traces
    3. Query WAL for root spans, check which traces have LLM spans
    4. Merge and deduplicate

    Filters for traces that have at least one span with
    attributes['openinference.span.kind'] = 'LLM'.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of root span dictionaries from LLM traces.
    """
    # Step 1: Get Parquet LLM trace IDs (indexed lookup - fast)
    parquet_llm_trace_ids = v4_repository.get_llm_trace_ids(service_name, limit * 2)

    # Step 2: Get Parquet root spans for LLM traces
    parquet_spans = []
    if parquet_llm_trace_ids:
        file_paths = v4_repository.get_file_paths_for_service(
            service_name,
            limit=limit * 2,
            is_root=True,
        )
        if file_paths:
            all_parquet_root_spans = datafusion_query.get_root_spans(
                service_name, file_paths, limit=limit * 2
            )
            parquet_spans = [
                span for span in all_parquet_root_spans if span["trace_id"] in parquet_llm_trace_ids
            ]

    # Step 3: Get WAL root spans and filter for LLM traces
    wal_spans = []
    wal_root_spans = await _get_wal_root_spans(service_name, limit * 2)

    if wal_root_spans:
        # Get unique trace IDs from WAL root spans
        wal_trace_ids = {span["trace_id"] for span in wal_root_spans}

        # For each WAL trace, check if it contains LLM spans
        wal_llm_trace_ids: set[str] = set()
        for trace_id in wal_trace_ids:
            trace_spans = await _get_wal_spans_by_trace(trace_id)
            for span in trace_spans:
                # Check if any span in trace has openinference.span.kind = 'LLM'
                attrs = span.get("attributes_json", {})
                if attrs.get("openinference.span.kind") == "LLM":
                    wal_llm_trace_ids.add(trace_id)
                    break

        # Filter WAL root spans to only those in LLM traces
        wal_spans = [span for span in wal_root_spans if span["trace_id"] in wal_llm_trace_ids]

    # Step 4: Merge Parquet and WAL results
    merged = _merge_spans(parquet_spans, wal_spans)

    logger.debug(
        "Merged LLM root spans",
        extra={
            "service_name": service_name,
            "parquet_llm_trace_count": len(parquet_llm_trace_ids),
            "parquet_span_count": len(parquet_spans),
            "wal_span_count": len(wal_spans),
            "merged_count": len(merged),
        },
    )

    return merged[:limit]


async def get_fused_workflow_spans(service_name: str, limit: int = 500) -> list[dict]:
    """Get workflow-type spans for a service from Parquet and WAL.

    Fusion query:
    1. Query Parquet for workflow spans (indexed by junjo_span_type)
    2. Query WAL for workflow spans
    3. Merge and deduplicate

    Filters spans where junjo_span_type = 'workflow'.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of workflow span dictionaries.
    """
    # Get file paths containing workflow spans (metadata-indexed)
    file_paths = v4_repository.get_file_paths_for_junjo_type(service_name, "workflow", limit=limit)

    # Query Parquet for workflow spans
    parquet_spans = []
    if file_paths:
        parquet_spans = datafusion_query.get_workflow_spans(service_name, file_paths, limit=limit)

    # Query WAL for workflow spans
    wal_spans = await _get_wal_workflow_spans(service_name, limit)

    # Merge results
    merged = _merge_spans(parquet_spans, wal_spans)

    logger.debug(
        "Merged workflow spans",
        extra={
            "service_name": service_name,
            "parquet_count": len(parquet_spans),
            "wal_count": len(wal_spans),
            "merged_count": len(merged),
        },
    )

    return merged[:limit]


async def get_fused_trace_spans(trace_id: str) -> list[dict]:
    """Get all spans for a specific trace from Parquet and WAL.

    Fusion query:
    1. Look up file paths containing this trace from DuckDB
    2. Query Parquet files for all spans in the trace
    3. Query WAL for spans in the trace
    4. Merge and deduplicate by span_id

    Args:
        trace_id: Trace ID (32-char hex string).

    Returns:
        List of span dictionaries ordered by start time DESC.
    """
    # Get file paths for this trace
    file_paths = v4_repository.get_file_paths_for_trace(trace_id)

    # Query Parquet for all spans in trace
    parquet_spans = []
    if file_paths:
        parquet_spans = datafusion_query.get_spans_by_trace_id(trace_id, file_paths)

    # Query WAL for spans in this trace
    wal_spans = await _get_wal_spans_by_trace(trace_id)

    # Merge results
    merged = _merge_spans(parquet_spans, wal_spans)

    logger.debug(
        "Merged trace spans",
        extra={
            "trace_id": trace_id,
            "parquet_count": len(parquet_spans),
            "wal_count": len(wal_spans),
            "merged_count": len(merged),
        },
    )

    return merged


async def get_fused_span(trace_id: str, span_id: str) -> dict | None:
    """Get a specific span by trace ID and span ID from Parquet or WAL.

    Fusion query:
    1. Look up file path(s) containing this span from DuckDB
    2. Query Parquet file for the specific span (prefer if found)
    3. If not in Parquet, check WAL

    Args:
        trace_id: Trace ID (32-char hex string).
        span_id: Span ID (16-char hex string).

    Returns:
        Span dictionary if found, None otherwise.
    """
    # Get file path for this span
    file_paths = v4_repository.get_file_paths_for_span(span_id)

    # Try Parquet first (source of truth)
    if file_paths:
        span = datafusion_query.get_span_by_id(span_id, trace_id, file_paths)
        if span:
            return span

    # If not in Parquet, check WAL
    wal_spans = await _get_wal_spans_by_trace(trace_id)
    for span in wal_spans:
        if span.get("span_id") == span_id:
            return span

    logger.debug(f"Span not found in Parquet or WAL: {span_id}")
    return None
