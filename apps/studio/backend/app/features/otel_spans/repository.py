"""Repository for querying OTEL spans from DuckDB.

Provides data access methods for span query endpoints.
Each method has a single responsibility following SRP.
"""

import json

from loguru import logger

from app.db_duckdb.db_config import get_connection


def _parse_json_fields(row: dict) -> dict:
    """Parse JSON string fields to Python dicts/lists.

    DuckDB returns JSON columns as strings, so we need to parse them.

    Args:
        row: Raw row dictionary from DuckDB.

    Returns:
        Row with JSON fields parsed.
    """
    json_fields = [
        "attributes_json",
        "events_json",
        "links_json",
        "junjo_wf_state_start",
        "junjo_wf_state_end",
        "junjo_wf_graph_structure",
    ]

    for field in json_fields:
        if field in row and row[field] is not None:
            if isinstance(row[field], str):
                try:
                    row[field] = json.loads(row[field])
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON field {field}: {row[field]}")

    return row


def get_distinct_service_names() -> list[str]:
    """Get list of all distinct service names from spans.

    Returns:
        List of service names in alphabetical order.

    Query: backend/api/otel/query_distinct_service_names.sql
    """
    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT DISTINCT service_name
            FROM spans
            ORDER BY service_name ASC
            """
        ).fetchall()

        return [row[0] for row in result]


def get_service_spans(service_name: str, limit: int = 500) -> list[dict]:
    """Get all spans for a service.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of span dictionaries.
    """
    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT
                trace_id, span_id, parent_span_id, service_name, name, kind,
                strftime(start_time, '%Y-%m-%dT%H:%M:%S.%f') || '+00:00' as start_time,
                strftime(end_time, '%Y-%m-%dT%H:%M:%S.%f') || '+00:00' as end_time,
                status_code, status_message, attributes_json, events_json, links_json,
                trace_flags, trace_state,
                junjo_id, junjo_parent_id, junjo_span_type,
                junjo_wf_state_start, junjo_wf_state_end, junjo_wf_graph_structure, junjo_wf_store_id
            FROM spans
            WHERE service_name = ?
            ORDER BY start_time DESC
            LIMIT ?
            """,
            [service_name, limit],
        ).fetchall()

        # Get column names
        columns = [desc[0] for desc in conn.description]

        # Convert rows to dictionaries and parse JSON fields
        return [_parse_json_fields(dict(zip(columns, row))) for row in result]


def get_root_spans(service_name: str, limit: int = 500) -> list[dict]:
    """Get root spans (no parent) for a service.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of root span dictionaries.

    Query: backend/api/otel/query_root_spans.sql
    """
    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT
                trace_id, span_id, parent_span_id, service_name, name, kind,
                strftime(start_time, '%Y-%m-%dT%H:%M:%S.%f') || '+00:00' as start_time,
                strftime(end_time, '%Y-%m-%dT%H:%M:%S.%f') || '+00:00' as end_time,
                status_code, status_message, attributes_json, events_json, links_json,
                trace_flags, trace_state,
                junjo_id, junjo_parent_id, junjo_span_type,
                junjo_wf_state_start, junjo_wf_state_end, junjo_wf_graph_structure, junjo_wf_store_id
            FROM spans
            WHERE service_name = ?
              AND parent_span_id IS NULL
            ORDER BY start_time DESC
            LIMIT ?
            """,
            [service_name, limit],
        ).fetchall()

        columns = [desc[0] for desc in conn.description]
        return [_parse_json_fields(dict(zip(columns, row))) for row in result]


def get_root_spans_with_llm(service_name: str, limit: int = 500) -> list[dict]:
    """Get root spans that are part of traces containing LLM operations.

    Filters for traces that have at least one span with
    attributes_json->>'openinference.span.kind' = 'LLM'.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of root span dictionaries from LLM traces.

    Query: backend/api/otel/query_root_spans_filtered.sql
    """
    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT
                trace_id, span_id, parent_span_id, service_name, name, kind,
                strftime(start_time, '%Y-%m-%dT%H:%M:%S.%f') || '+00:00' as start_time,
                strftime(end_time, '%Y-%m-%dT%H:%M:%S.%f') || '+00:00' as end_time,
                status_code, status_message, attributes_json, events_json, links_json,
                trace_flags, trace_state,
                junjo_id, junjo_parent_id, junjo_span_type,
                junjo_wf_state_start, junjo_wf_state_end, junjo_wf_graph_structure, junjo_wf_store_id
            FROM spans
            WHERE service_name = ?
              AND parent_span_id IS NULL
              AND trace_id IN (
                SELECT trace_id
                FROM spans
                WHERE json_extract(attributes_json, '$.\"openinference.span.kind\"') = '"LLM"'
              )
            ORDER BY start_time DESC
            LIMIT ?
            """,
            [service_name, limit],
        ).fetchall()

        columns = [desc[0] for desc in conn.description]
        return [_parse_json_fields(dict(zip(columns, row))) for row in result]


def get_workflow_spans(service_name: str, limit: int = 500) -> list[dict]:
    """Get workflow-type spans for a service.

    Filters spans where junjo_span_type = 'workflow'.

    Args:
        service_name: Name of the service to query.
        limit: Maximum number of spans to return.

    Returns:
        List of workflow span dictionaries.

    Query: backend/api/otel/query_spans_type_workflow.sql
    """
    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT
                trace_id, span_id, parent_span_id, service_name, name, kind,
                strftime(start_time, '%Y-%m-%dT%H:%M:%S.%f') || '+00:00' as start_time,
                strftime(end_time, '%Y-%m-%dT%H:%M:%S.%f') || '+00:00' as end_time,
                status_code, status_message, attributes_json, events_json, links_json,
                trace_flags, trace_state,
                junjo_id, junjo_parent_id, junjo_span_type,
                junjo_wf_state_start, junjo_wf_state_end, junjo_wf_graph_structure, junjo_wf_store_id
            FROM spans
            WHERE junjo_span_type = 'workflow'
              AND service_name = ?
            ORDER BY start_time DESC
            LIMIT ?
            """,
            [service_name, limit],
        ).fetchall()

        columns = [desc[0] for desc in conn.description]
        return [_parse_json_fields(dict(zip(columns, row))) for row in result]


def get_trace_spans(trace_id: str) -> list[dict]:
    """Get all spans for a specific trace.

    Args:
        trace_id: Trace ID (32-char hex string).

    Returns:
        List of span dictionaries ordered by start time.

    Query: backend/api/otel/query_nested_spans.sql
    """
    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT
                trace_id, span_id, parent_span_id, service_name, name, kind,
                strftime(start_time, '%Y-%m-%dT%H:%M:%S.%f') || '+00:00' as start_time,
                strftime(end_time, '%Y-%m-%dT%H:%M:%S.%f') || '+00:00' as end_time,
                status_code, status_message, attributes_json, events_json, links_json,
                trace_flags, trace_state,
                junjo_id, junjo_parent_id, junjo_span_type,
                junjo_wf_state_start, junjo_wf_state_end, junjo_wf_graph_structure, junjo_wf_store_id
            FROM spans
            WHERE trace_id = ?
            ORDER BY start_time DESC
            """,
            [trace_id],
        ).fetchall()

        columns = [desc[0] for desc in conn.description]
        return [_parse_json_fields(dict(zip(columns, row))) for row in result]


def get_span(trace_id: str, span_id: str) -> dict | None:
    """Get a specific span by trace ID and span ID.

    Args:
        trace_id: Trace ID (32-char hex string).
        span_id: Span ID (16-char hex string).

    Returns:
        Span dictionary if found, None otherwise.

    Query: backend/api/otel/query_span.sql
    """
    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT
                trace_id, span_id, parent_span_id, service_name, name, kind,
                strftime(start_time, '%Y-%m-%dT%H:%M:%S.%f') || '+00:00' as start_time,
                strftime(end_time, '%Y-%m-%dT%H:%M:%S.%f') || '+00:00' as end_time,
                status_code, status_message, attributes_json, events_json, links_json,
                trace_flags, trace_state,
                junjo_id, junjo_parent_id, junjo_span_type,
                junjo_wf_state_start, junjo_wf_state_end, junjo_wf_graph_structure, junjo_wf_store_id
            FROM spans
            WHERE trace_id = ?
              AND span_id = ?
            """,
            [trace_id, span_id],
        ).fetchone()

        if result is None:
            return None

        columns = [desc[0] for desc in conn.description]
        return _parse_json_fields(dict(zip(columns, result)))
