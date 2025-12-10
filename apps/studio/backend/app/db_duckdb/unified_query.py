"""Unified DataFusion query engine for three-tier span data (Cold/Warm/Hot).

Three-Tier Architecture:
- COLD: Parquet files from full WAL flushes (indexed in DuckDB)
- WARM: Incremental parquet snapshots in tmp/ (not indexed, globbed)
- HOT: Live SQLite data since last warm snapshot (gRPC Arrow IPC)

Combines all three tiers in a single DataFusion query with deduplication.
Priority: Cold > Warm > Hot (same span_id).

Usage:
    query = UnifiedSpanQuery()
    query.register_cold(file_paths)         # From DuckDB metadata
    query.register_warm()                    # Glob tmp/*.parquet
    query.register_hot(hot_arrow_table)     # From gRPC
    results = query.query_spans(trace_id="abc123")
"""

import glob
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import datafusion
import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger

from app.config.settings import settings


class UnifiedSpanQuery:
    """Unified query engine for three-tier span data (Cold/Warm/Hot).

    Registers all three data sources as DataFusion tables and executes SQL queries
    that merge and deduplicate data (Cold > Warm > Hot precedence).
    """

    def __init__(self) -> None:
        """Create a new UnifiedSpanQuery instance."""
        self.ctx = datafusion.SessionContext()
        self._cold_registered = False
        self._warm_registered = False
        self._hot_registered = False
        # Legacy compatibility
        self._parquet_registered = False
        self._wal_registered = False
        # Warm directory path
        self._warm_dir = Path(settings.parquet_indexer.parquet_storage_path) / "tmp"

    def register_parquet(self, file_paths: list[str]) -> None:
        """Register Parquet files as 'parquet_spans' table.

        Args:
            file_paths: List of Parquet file paths to query
        """
        if not file_paths:
            # No files to register, skip (Parquet query will be skipped)
            self._parquet_registered = False
            logger.debug("No Parquet files to register")
            return

        try:
            # Deregister if exists from previous query
            try:
                self.ctx.deregister_table("parquet_spans")
            except Exception:
                pass

            # Read all files into a single Arrow table
            arrow_table = pq.read_table(file_paths)

            # Create DataFusion DataFrame and register
            df = self.ctx.from_arrow(arrow_table)
            self.ctx.register_table("parquet_spans", df)
            self._parquet_registered = True

            logger.debug(
                "Registered Parquet files",
                extra={"file_count": len(file_paths), "row_count": arrow_table.num_rows},
            )

        except Exception as e:
            logger.error(f"Failed to register Parquet files: {e}")
            self._parquet_registered = False

    def register_wal(self, wal_table: pa.Table) -> None:
        """Register WAL Arrow table as 'wal_spans' table.

        Args:
            wal_table: PyArrow Table from ingestion client's get_wal_spans_arrow()
        """
        try:
            # Deregister if exists from previous query
            try:
                self.ctx.deregister_table("wal_spans")
            except Exception:
                pass

            # Check if WAL table has actual data (must have columns AND rows)
            # An empty pa.table({}) has no columns, so can't be used in UNION
            has_data = wal_table.num_columns > 0 and wal_table.num_rows > 0

            if has_data:
                df = self.ctx.from_arrow(wal_table)
                self.ctx.register_table("wal_spans", df)
                self._wal_registered = True
                logger.debug("Registered WAL table", extra={"row_count": wal_table.num_rows})
            else:
                # WAL is empty, skip registration (Parquet-only query)
                self._wal_registered = False
                logger.debug("WAL table empty, skipping registration")

        except Exception as e:
            logger.error(f"Failed to register WAL table: {e}")
            raise

    # =========================================================================
    # Three-Tier Architecture Methods (Cold/Warm/Hot)
    # =========================================================================

    def register_cold(self, file_paths: list[str]) -> None:
        """Register COLD tier Parquet files as 'cold_spans' table.

        Cold tier contains data from full WAL flushes, indexed in DuckDB.

        Args:
            file_paths: List of Parquet file paths from DuckDB metadata
        """
        if not file_paths:
            self._cold_registered = False
            logger.debug("No cold Parquet files to register")
            return

        try:
            try:
                self.ctx.deregister_table("cold_spans")
            except Exception:
                pass

            arrow_table = pq.read_table(file_paths)
            df = self.ctx.from_arrow(arrow_table)
            self.ctx.register_table("cold_spans", df)
            self._cold_registered = True

            logger.debug(
                "Registered COLD tier files",
                extra={"file_count": len(file_paths), "row_count": arrow_table.num_rows},
            )

        except Exception as e:
            logger.error(f"Failed to register cold files: {e}")
            self._cold_registered = False

    def register_warm(self) -> list[str]:
        """Register WARM tier Parquet files as 'warm_spans' table.

        Warm tier contains incremental snapshots from tmp/, not indexed in DuckDB.
        Uses glob pattern to find all warm_*.parquet files.

        Returns:
            List of warm file paths found (for logging)
        """
        try:
            try:
                self.ctx.deregister_table("warm_spans")
            except Exception:
                pass

            # Glob for warm parquet files
            warm_pattern = str(self._warm_dir / "warm_*.parquet")
            warm_files = glob.glob(warm_pattern)

            if not warm_files:
                self._warm_registered = False
                logger.debug("No warm Parquet files found")
                return []

            arrow_table = pq.read_table(warm_files)
            df = self.ctx.from_arrow(arrow_table)
            self.ctx.register_table("warm_spans", df)
            self._warm_registered = True

            logger.debug(
                "Registered WARM tier files",
                extra={"file_count": len(warm_files), "row_count": arrow_table.num_rows},
            )

            return warm_files

        except Exception as e:
            logger.error(f"Failed to register warm files: {e}")
            self._warm_registered = False
            return []

    def register_hot(self, hot_table: pa.Table) -> None:
        """Register HOT tier Arrow table as 'hot_spans' table.

        Hot tier contains live data since last warm snapshot, from gRPC.

        Args:
            hot_table: PyArrow Table from ingestion client's get_hot_spans_arrow()
        """
        try:
            try:
                self.ctx.deregister_table("hot_spans")
            except Exception:
                pass

            has_data = hot_table.num_columns > 0 and hot_table.num_rows > 0

            if has_data:
                df = self.ctx.from_arrow(hot_table)
                self.ctx.register_table("hot_spans", df)
                self._hot_registered = True
                logger.debug("Registered HOT tier table", extra={"row_count": hot_table.num_rows})
            else:
                self._hot_registered = False
                logger.debug("HOT tier table empty, skipping registration")

        except Exception as e:
            logger.error(f"Failed to register hot table: {e}")
            raise

    def query_distinct_service_names(self) -> list[str]:
        """Get distinct service names across all three tiers.

        Uses UNION to deduplicate service names automatically.

        Returns:
            Sorted list of unique service names
        """
        sources = []
        if self._cold_registered:
            sources.append("SELECT DISTINCT service_name FROM cold_spans")
        if self._warm_registered:
            sources.append("SELECT DISTINCT service_name FROM warm_spans")
        if self._hot_registered:
            sources.append("SELECT DISTINCT service_name FROM hot_spans")

        if not sources:
            return []

        # UNION automatically deduplicates
        union_sql = " UNION ".join(sources)
        sql = f"SELECT service_name FROM ({union_sql}) ORDER BY service_name"

        try:
            df = self.ctx.sql(sql)
            batches = df.collect()

            services = []
            for batch in batches:
                table = batch.to_pydict()
                services.extend(table.get("service_name", []))

            return services

        except Exception as e:
            logger.error(f"Failed to query distinct service names: {e}")
            return []

    def query_spans_three_tier(
        self,
        *,
        trace_id: str | None = None,
        service_name: str | None = None,
        root_only: bool = False,
        workflow_only: bool = False,
        order_by: str = "start_time DESC",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Query unified spans across all three tiers with deduplication.

        Priority: Cold > Warm > Hot (same span_id, Cold wins).

        Args:
            trace_id: Filter by trace ID
            service_name: Filter by service name
            root_only: Only return root spans (no parent)
            workflow_only: Only return workflow spans (post-filter)
            order_by: SQL ORDER BY clause
            limit: Maximum rows to return

        Returns:
            List of span dictionaries in API format
        """
        if not self._cold_registered and not self._warm_registered and not self._hot_registered:
            logger.warning("No data sources registered for three-tier query")
            return []

        # Build WHERE clauses
        where_clauses: list[str] = []
        if trace_id:
            where_clauses.append(f"trace_id = '{trace_id}'")
        if service_name:
            where_clauses.append(f"service_name = '{service_name}'")
        if root_only:
            where_clauses.append("(parent_span_id IS NULL OR parent_span_id = '')")

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        sql = self._build_three_tier_query(where_sql, order_by, limit)

        logger.debug(f"Three-tier SQL: {sql[:500]}...")

        try:
            df = self.ctx.sql(sql)
            batches = df.collect()

            rows = self._convert_batches_to_api_format(batches)

            # Post-filter for workflow spans if needed
            if workflow_only:
                rows = [
                    r
                    for r in rows
                    if r.get("attributes_json", {}).get("junjo.span_type") == "workflow"
                ]
                if limit:
                    rows = rows[:limit]

            return rows

        except Exception as e:
            logger.error(f"Three-tier query failed: {e}")
            raise

    def _build_three_tier_query(self, where_sql: str, order_by: str, limit: int | None) -> str:
        """Build SQL that merges all three tiers with deduplication."""
        # Build UNION of available tiers
        tier_queries = []

        select_cols = """
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
            resource_attributes"""

        if self._cold_registered:
            tier_queries.append(f"""
                SELECT {select_cols}, 'cold' as _tier
                FROM cold_spans
                WHERE {where_sql}
            """)

        if self._warm_registered:
            tier_queries.append(f"""
                SELECT {select_cols}, 'warm' as _tier
                FROM warm_spans
                WHERE {where_sql}
            """)

        if self._hot_registered:
            tier_queries.append(f"""
                SELECT {select_cols}, 'hot' as _tier
                FROM hot_spans
                WHERE {where_sql}
            """)

        if not tier_queries:
            return "SELECT 1 WHERE 1=0"  # Empty result

        union_sql = " UNION ALL ".join(tier_queries)

        # Deduplicate: cold > warm > hot priority
        sql = f"""
        WITH combined AS ({union_sql}),
        ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY span_id
                    ORDER BY CASE _tier
                        WHEN 'cold' THEN 0
                        WHEN 'warm' THEN 1
                        ELSE 2
                    END
                ) as _rn
            FROM combined
        )
        SELECT
            span_id,
            trace_id,
            parent_span_id,
            service_name,
            name,
            span_kind,
            start_time_ns,
            end_time_ns,
            duration_ns,
            status_code,
            status_message,
            attributes,
            events,
            resource_attributes
        FROM ranked
        WHERE _rn = 1
        ORDER BY {order_by.replace("start_time", "start_time_ns")}
        """

        if limit:
            sql += f" LIMIT {limit}"

        return sql

    def query_spans(
        self,
        *,
        trace_id: str | None = None,
        service_name: str | None = None,
        root_only: bool = False,
        workflow_only: bool = False,
        order_by: str = "start_time DESC",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Query unified spans with deduplication (Parquet wins).

        Args:
            trace_id: Filter by trace ID
            service_name: Filter by service name
            root_only: Only return root spans (no parent)
            workflow_only: Only return workflow spans (post-filter)
            order_by: SQL ORDER BY clause
            limit: Maximum rows to return

        Returns:
            List of span dictionaries in API format
        """
        if not self._parquet_registered and not self._wal_registered:
            logger.warning("No data sources registered")
            return []

        # Build WHERE clauses
        where_clauses: list[str] = []
        if trace_id:
            where_clauses.append(f"trace_id = '{trace_id}'")
        if service_name:
            where_clauses.append(f"service_name = '{service_name}'")
        if root_only:
            where_clauses.append("(parent_span_id IS NULL OR parent_span_id = '')")

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Build unified query with deduplication
        # Use UNION ALL with ROW_NUMBER to deduplicate (Parquet wins)
        if self._parquet_registered and self._wal_registered:
            sql = self._build_unified_query(where_sql, order_by, limit)
        elif self._parquet_registered:
            sql = self._build_parquet_only_query(where_sql, order_by, limit)
        else:
            sql = self._build_wal_only_query(where_sql, order_by, limit)

        logger.debug(f"Unified SQL: {sql[:500]}...")

        try:
            df = self.ctx.sql(sql)
            batches = df.collect()

            rows = self._convert_batches_to_api_format(batches)

            # Post-filter for workflow spans if needed
            if workflow_only:
                rows = [
                    r
                    for r in rows
                    if r.get("attributes_json", {}).get("junjo.span_type") == "workflow"
                ]
                if limit:
                    rows = rows[:limit]

            return rows

        except Exception as e:
            logger.error(f"Unified query failed: {e}")
            raise

    def _build_unified_query(self, where_sql: str, order_by: str, limit: int | None) -> str:
        """Build SQL that merges WAL and Parquet with deduplication."""
        # Note: Parquet has timestamps as nanosecond timestamps, WAL has them too
        # We cast to BIGINT for consistent handling
        sql = f"""
        WITH combined AS (
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
                resource_attributes,
                'parquet' as source
            FROM parquet_spans
            WHERE {where_sql}

            UNION ALL

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
                resource_attributes,
                'wal' as source
            FROM wal_spans
            WHERE {where_sql}
        ),
        ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY span_id
                    ORDER BY CASE source WHEN 'parquet' THEN 0 ELSE 1 END
                ) as rn
            FROM combined
        )
        SELECT
            span_id,
            trace_id,
            parent_span_id,
            service_name,
            name,
            span_kind,
            start_time_ns,
            end_time_ns,
            duration_ns,
            status_code,
            status_message,
            attributes,
            events,
            resource_attributes
        FROM ranked
        WHERE rn = 1
        ORDER BY {order_by.replace("start_time", "start_time_ns")}
        """

        if limit:
            sql += f" LIMIT {limit}"

        return sql

    def _build_parquet_only_query(self, where_sql: str, order_by: str, limit: int | None) -> str:
        """Build SQL for Parquet-only query."""
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
        FROM parquet_spans
        WHERE {where_sql}
        ORDER BY {order_by.replace("start_time", "start_time_ns")}
        """

        if limit:
            sql += f" LIMIT {limit}"

        return sql

    def _build_wal_only_query(self, where_sql: str, order_by: str, limit: int | None) -> str:
        """Build SQL for WAL-only query."""
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
        FROM wal_spans
        WHERE {where_sql}
        ORDER BY {order_by.replace("start_time", "start_time_ns")}
        """

        if limit:
            sql += f" LIMIT {limit}"

        return sql

    def _convert_batches_to_api_format(self, batches: list[pa.RecordBatch]) -> list[dict[str, Any]]:
        """Convert Arrow RecordBatches to API response format."""
        rows: list[dict[str, Any]] = []

        for batch in batches:
            table = batch.to_pydict()
            num_rows = len(table.get("span_id", []))

            for i in range(num_rows):
                row = _convert_row_to_api_format(table, i)
                rows.append(row)

        return rows


def _convert_row_to_api_format(table: dict[str, list], idx: int) -> dict[str, Any]:
    """Convert a result row to API response format."""
    span_id = table["span_id"][idx]
    trace_id = table["trace_id"][idx]
    parent_span_id = table["parent_span_id"][idx]
    service_name = table["service_name"][idx]
    name = table["name"][idx]
    span_kind = table["span_kind"][idx]
    start_time_ns = table["start_time_ns"][idx]
    end_time_ns = table["end_time_ns"][idx]
    status_code = table["status_code"][idx]
    status_message = table["status_message"][idx]
    attributes_str = table["attributes"][idx]
    events_str = table["events"][idx]

    # Parse JSON fields
    attributes = _parse_json_safe(attributes_str, {})
    events = _parse_json_safe(events_str, [])

    # Format timestamps
    start_time_str = _format_timestamp_ns(start_time_ns)
    end_time_str = _format_timestamp_ns(end_time_ns)

    # Map span_kind int to string
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
        "attributes_json": attributes,
        "events_json": events,
        "links_json": [],
        "trace_flags": 0,
        "trace_state": None,
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


def _format_timestamp_ns(ts_ns: int | None) -> str:
    """Format nanosecond timestamp to ISO8601 string with timezone."""
    if ts_ns is None or ts_ns == 0:
        return ""
    seconds = ts_ns // 1_000_000_000
    remaining_ns = ts_ns % 1_000_000_000
    microseconds = remaining_ns // 1000
    dt = datetime.fromtimestamp(seconds, tz=UTC)
    dt = dt.replace(microsecond=microseconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "+00:00"
