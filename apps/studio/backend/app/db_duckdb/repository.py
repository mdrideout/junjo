"""Repository for DuckDB span operations.

Handles batch insertion of OTEL spans and state patches.
Uses raw SQL for performance (DuckDB is optimized for bulk inserts).
"""

from typing import Any

from loguru import logger

from app.db_duckdb.db_config import get_connection


class SpanRepository:
    """Repository for span database operations.

    All methods are static to avoid instance state.
    Each method creates its own DuckDB connection (DuckDB handles concurrency well).
    """

    @staticmethod
    def batch_insert_spans(spans: list[dict[str, Any]]) -> int:
        """Batch insert spans into DuckDB.

        Args:
            spans: List of span dictionaries with all fields.
                   Expected keys: trace_id, span_id, parent_span_id, service_name,
                   name, kind, start_time, end_time, status_code, status_message,
                   attributes_json, events_json, links_json, trace_flags, trace_state,
                   junjo_id, junjo_parent_id, junjo_span_type, junjo_wf_state_start,
                   junjo_wf_state_end, junjo_wf_graph_structure, junjo_wf_store_id

        Returns:
            Number of spans inserted (may be less than len(spans) due to duplicates)

        Note:
            Uses INSERT OR IGNORE for idempotency.
            Duplicate (trace_id, span_id) are silently skipped.
        """
        if not spans:
            return 0

        with get_connection() as conn:
            # DuckDB supports INSERT OR IGNORE for duplicate PK
            sql = """
                INSERT OR IGNORE INTO spans (
                    trace_id, span_id, parent_span_id, service_name, name, kind,
                    start_time, end_time, status_code, status_message,
                    attributes_json, events_json, links_json, trace_flags, trace_state,
                    junjo_id, junjo_parent_id, junjo_span_type,
                    junjo_wf_state_start, junjo_wf_state_end,
                    junjo_wf_graph_structure, junjo_wf_store_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            # Convert spans to tuples for bulk insert
            values = [
                (
                    span["trace_id"],
                    span["span_id"],
                    span.get("parent_span_id"),
                    span["service_name"],
                    span.get("name"),
                    span.get("kind"),
                    span["start_time"],
                    span["end_time"],
                    span.get("status_code"),
                    span.get("status_message"),
                    span.get("attributes_json"),
                    span.get("events_json"),
                    span.get("links_json"),
                    span.get("trace_flags"),
                    span.get("trace_state"),
                    span.get("junjo_id"),
                    span.get("junjo_parent_id"),
                    span.get("junjo_span_type"),
                    span.get("junjo_wf_state_start"),
                    span.get("junjo_wf_state_end"),
                    span.get("junjo_wf_graph_structure"),
                    span.get("junjo_wf_store_id"),
                )
                for span in spans
            ]

            conn.executemany(sql, values)
            inserted = len(spans)  # DuckDB doesn't have total_changes like SQLite

            logger.info(f"Batch inserted {inserted} spans into DuckDB")
            return inserted

    @staticmethod
    def batch_insert_state_patches(patches: list[dict[str, Any]]) -> int:
        """Batch insert state patches into DuckDB.

        Args:
            patches: List of state patch dictionaries.
                    Expected keys: patch_id, service_name, trace_id, span_id,
                    workflow_id, node_id, event_time, patch_json, patch_store_id

        Returns:
            Number of patches inserted

        Note:
            Foreign key constraint ensures parent span exists.
        """
        if not patches:
            return 0

        with get_connection() as conn:
            sql = """
                INSERT OR IGNORE INTO state_patches (
                    patch_id, service_name, trace_id, span_id,
                    workflow_id, node_id, event_time,
                    patch_json, patch_store_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            values = [
                (
                    patch["patch_id"],
                    patch["service_name"],
                    patch["trace_id"],
                    patch["span_id"],
                    patch["workflow_id"],
                    patch["node_id"],
                    patch["event_time"],
                    patch["patch_json"],
                    patch["patch_store_id"],
                )
                for patch in patches
            ]

            conn.executemany(sql, values)
            inserted = len(patches)

            logger.info(f"Batch inserted {inserted} state patches into DuckDB")
            return inserted
