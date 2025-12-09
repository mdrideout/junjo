"""DataFusion query engine for Parquet file access.

Provides SQL-based querying of span data stored in Parquet files.
DataFusion reads Parquet directly without loading into memory.

Usage pattern:
1. Get file paths from DuckDB span_metadata (filtered by trace_id, service, etc.)
2. Use DataFusion to query full span data from those Parquet files
3. Convert results to API response format
"""

import json
from datetime import UTC, datetime
from typing import Any

import datafusion
import pyarrow.parquet as pq
from loguru import logger

# Module-level context (lazy initialization)
_ctx: datafusion.SessionContext | None = None


def get_context() -> datafusion.SessionContext:
    """Get or create a DataFusion SessionContext.

    Returns a singleton context for the application lifetime.
    Context is stateless between queries (tables registered per-query).
    """
    global _ctx
    if _ctx is None:
        _ctx = datafusion.SessionContext()
        logger.debug("Created DataFusion SessionContext")
    return _ctx


def query_spans_from_parquet(
    file_paths: list[str],
    filter_sql: str | None = None,
    order_by: str = "start_time DESC",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Query span data from Parquet files using DataFusion.

    Uses PyArrow to efficiently read multiple Parquet files into a single Arrow table,
    then DataFusion for SQL queries with zero-copy data transfer.

    Args:
        file_paths: List of Parquet file paths to query
        filter_sql: Optional SQL WHERE clause (without WHERE keyword)
        order_by: SQL ORDER BY clause (without ORDER BY keyword)
        limit: Optional row limit

    Returns:
        List of span dictionaries with parsed JSON fields
    """
    if not file_paths:
        return []

    ctx = get_context()
    table_name = "spans"

    try:
        # Deregister if exists from previous query
        try:
            ctx.deregister_table(table_name)
        except Exception:
            pass

        # Use PyArrow to read all files into a single Arrow table
        # This is more efficient than iterating file-by-file
        arrow_table = pq.read_table(file_paths)

        # Create DataFusion DataFrame from Arrow table (zero-copy)
        df = ctx.from_arrow(arrow_table)

        # Register as a table so we can run SQL queries
        ctx.register_table(table_name, df)

        return _execute_span_query(ctx, table_name, filter_sql, order_by, limit)

    except Exception as e:
        logger.error(f"DataFusion query failed: {e}")
        raise


def _execute_span_query(
    ctx: datafusion.SessionContext,
    table_name: str,
    filter_sql: str | None,
    order_by: str,
    limit: int | None,
) -> list[dict[str, Any]]:
    """Execute a span query and convert results to dicts."""
    # Build SQL query
    # Cast timestamps to INT64 (nanoseconds) since pyarrow can't convert ns timestamps
    sql = f"""
        SELECT
            span_id,
            trace_id,
            parent_span_id,
            service_name,
            name,
            span_kind,
            CAST(start_time AS BIGINT) as start_time_ns,
            CAST(end_time AS BIGINT) as end_time_ns,
            duration_ns,
            status_code,
            status_message,
            attributes,
            events,
            resource_attributes
        FROM {table_name}
    """

    if filter_sql:
        sql += f" WHERE {filter_sql}"

    if order_by:
        # Adjust order by to use original column name
        sql += f" ORDER BY {order_by}"

    if limit:
        sql += f" LIMIT {limit}"

    logger.debug(f"DataFusion SQL: {sql}")

    # Execute query
    df = ctx.sql(sql)
    batches = df.collect()

    # Convert to Python dicts
    rows: list[dict[str, Any]] = []
    for batch in batches:
        # Convert RecordBatch to Python - now timestamps are BIGINT
        table = batch.to_pydict()
        num_rows = len(table.get("span_id", []))

        for i in range(num_rows):
            row = _convert_parquet_row_to_api_format(table, i)
            rows.append(row)

    return rows


def _convert_parquet_row_to_api_format(table: dict[str, list], idx: int) -> dict[str, Any]:
    """Convert a Parquet row to the API response format.

    Handles:
    - Column name mapping (span_kind -> kind, attributes -> attributes_json)
    - Timestamp formatting to ISO8601
    - JSON string parsing
    - Extracting junjo_* fields from attributes
    """
    # Get raw values
    span_id = table["span_id"][idx]
    trace_id = table["trace_id"][idx]
    parent_span_id = table["parent_span_id"][idx]
    service_name = table["service_name"][idx]
    name = table["name"][idx]
    span_kind = table["span_kind"][idx]
    start_time_ns = table["start_time_ns"][idx]  # BIGINT nanoseconds from SQL cast
    end_time_ns = table["end_time_ns"][idx]  # BIGINT nanoseconds from SQL cast
    status_code = table["status_code"][idx]
    status_message = table["status_message"][idx]
    attributes_str = table["attributes"][idx]
    events_str = table["events"][idx]
    _ = table["resource_attributes"][idx]  # Available but not used in API response

    # Parse JSON fields - pass through unchanged (no junjo extraction)
    # Frontend SpanAccessor handles junjo field extraction
    attributes = _parse_json_safe(attributes_str, {})
    events = _parse_json_safe(events_str, [])

    # Format timestamps as ISO8601 with timezone
    start_time_str = _format_timestamp(start_time_ns)
    end_time_str = _format_timestamp(end_time_ns)

    # Map span_kind int to string (matching V3 behavior)
    kind_map = {0: "INTERNAL", 1: "SERVER", 2: "CLIENT", 3: "PRODUCER", 4: "CONSUMER"}
    kind_str = kind_map.get(span_kind, "INTERNAL")

    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "service_name": service_name,
        "name": name,
        "kind": kind_str,
        "start_time": start_time_str,
        "end_time": end_time_str,
        "status_code": str(status_code),
        "status_message": status_message or "",
        "attributes_json": attributes,  # Contains junjo.* fields - frontend extracts them
        "events_json": events,
        "links_json": [],  # Not in Parquet schema
        "trace_flags": 0,  # Not in Parquet schema
        "trace_state": None,  # Not in Parquet schema
    }


def _parse_json_safe(value: str | None, default: Any) -> Any:
    """Parse JSON string safely, returning default on failure."""
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _format_timestamp(ts: Any) -> str:
    """Format timestamp to ISO8601 string with timezone.

    Handles various timestamp formats from DataFusion/Arrow.
    """
    if ts is None:
        return ""

    # If already a string, return as-is
    if isinstance(ts, str):
        return ts

    # If datetime object
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts.strftime("%Y-%m-%dT%H:%M:%S.%f") + "+00:00"

    # If nanosecond integer
    if isinstance(ts, int):
        seconds = ts // 1_000_000_000
        remaining_ns = ts % 1_000_000_000
        microseconds = remaining_ns // 1000
        dt = datetime.fromtimestamp(seconds, tz=UTC)
        dt = dt.replace(microsecond=microseconds)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "+00:00"

    # Fallback - try to convert to string
    return str(ts)


# Convenience functions for common queries


def get_spans_by_trace_id(trace_id: str, file_paths: list[str]) -> list[dict[str, Any]]:
    """Get all spans for a trace from Parquet files.

    Args:
        trace_id: The trace ID to filter by
        file_paths: Parquet files that may contain this trace

    Returns:
        List of span dicts ordered by start_time DESC
    """
    return query_spans_from_parquet(
        file_paths=file_paths,
        filter_sql=f"trace_id = '{trace_id}'",
        order_by="start_time DESC",
    )


def get_span_by_id(span_id: str, trace_id: str, file_paths: list[str]) -> dict[str, Any] | None:
    """Get a single span by ID from Parquet files.

    Args:
        span_id: The span ID to find
        trace_id: The trace ID (for filtering)
        file_paths: Parquet files that may contain this span

    Returns:
        Span dict if found, None otherwise
    """
    results = query_spans_from_parquet(
        file_paths=file_paths,
        filter_sql=f"trace_id = '{trace_id}' AND span_id = '{span_id}'",
        limit=1,
    )
    return results[0] if results else None


def get_root_spans(
    service_name: str, file_paths: list[str], limit: int = 500
) -> list[dict[str, Any]]:
    """Get root spans (no parent) for a service from Parquet files.

    Args:
        service_name: Service to filter by
        file_paths: Parquet files that may contain spans
        limit: Maximum spans to return

    Returns:
        List of root span dicts ordered by start_time DESC
    """
    return query_spans_from_parquet(
        file_paths=file_paths,
        filter_sql=f"service_name = '{service_name}' AND (parent_span_id IS NULL OR parent_span_id = '')",
        order_by="start_time DESC",
        limit=limit,
    )


def get_service_spans(
    service_name: str, file_paths: list[str], limit: int = 500
) -> list[dict[str, Any]]:
    """Get all spans for a service from Parquet files.

    Args:
        service_name: Service to filter by
        file_paths: Parquet files that may contain spans
        limit: Maximum spans to return

    Returns:
        List of span dicts ordered by start_time DESC
    """
    return query_spans_from_parquet(
        file_paths=file_paths,
        filter_sql=f"service_name = '{service_name}'",
        order_by="start_time DESC",
        limit=limit,
    )


def get_workflow_spans(
    service_name: str, file_paths: list[str], limit: int = 500
) -> list[dict[str, Any]]:
    """Get workflow spans for a service from Parquet files.

    Filters for spans where junjo.span_type = 'workflow' in attributes.

    Args:
        service_name: Service to filter by
        file_paths: Parquet files that may contain workflow spans
        limit: Maximum spans to return

    Returns:
        List of workflow span dicts ordered by start_time DESC
    """
    # Query all spans from the files (attributes filter done in Python)
    all_spans = query_spans_from_parquet(
        file_paths=file_paths,
        filter_sql=f"service_name = '{service_name}'",
        order_by="start_time DESC",
        limit=limit * 2,  # Fetch more since we filter
    )

    # Filter for workflow spans - junjo.span_type is in attributes_json
    workflow_spans = [
        span
        for span in all_spans
        if span.get("attributes_json", {}).get("junjo.span_type") == "workflow"
    ]

    return workflow_spans[:limit]
