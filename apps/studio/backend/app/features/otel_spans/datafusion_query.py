"""Unified DataFusion query engine for two-tier span data (COLD/HOT).

Two-Tier Architecture (Rust ingestion):
- COLD: Parquet files from WAL flushes (selected via SQLite metadata index)
- HOT: On-demand Parquet snapshot (from PrepareHotSnapshot RPC)

Combines both tiers in a single DataFusion query with deduplication.
Priority: COLD > HOT for the same (trace_id, span_id).

Usage:
    query = UnifiedSpanQuery()
    query.register_cold(file_paths)              # from SQLite metadata
    query.register_hot("/path/to/snapshot.parquet")  # from PrepareHotSnapshot RPC
    spans = query.query_spans_two_tier(trace_id="abc123")
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import datafusion
import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger


class UnifiedSpanQuery:
    """Unified query engine for two-tier span data (Cold/Hot).

    Registers both data sources as DataFusion tables and executes SQL queries
    that merge and deduplicate data (Cold > Hot precedence).
    """

    def __init__(self) -> None:
        """Create a new UnifiedSpanQuery instance."""
        self.ctx = datafusion.SessionContext()
        self._cold_registered = False
        self._hot_registered = False

    def _filter_nonempty_parquet_files(
        self, file_paths: list[str], *, table_name: str
    ) -> list[str]:
        """Filter to existing, non-empty .parquet files.

        DataFusion's Python binding registers missing/empty files without raising and
        assigns an empty schema, which later causes "column not found" errors.
        """
        if not file_paths:
            return []

        seen: set[str] = set()
        valid: list[str] = []

        for file_path in file_paths:
            if not file_path:
                continue
            if file_path in seen:
                continue
            seen.add(file_path)

            path = Path(file_path)

            # DataFusion uses file_extension filtering internally; enforce .parquet inputs.
            if path.suffix.lower() != ".parquet":
                logger.warning(
                    "Skipping non-parquet path during registration",
                    extra={"table": table_name, "file_path": file_path},
                )
                continue

            try:
                stat = path.stat()
            except OSError as e:
                logger.warning(
                    "Skipping missing/unreadable parquet path during registration",
                    extra={
                        "table": table_name,
                        "file_path": file_path,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                continue

            if not path.is_file():
                logger.warning(
                    "Skipping non-file parquet path during registration",
                    extra={"table": table_name, "file_path": file_path},
                )
                continue

            if stat.st_size <= 0:
                logger.warning(
                    "Skipping empty parquet file during registration",
                    extra={"table": table_name, "file_path": file_path},
                )
                continue

            valid.append(file_path)

        return valid

    def _try_register_parquet(self, table_name: str, file_paths: list[str]) -> bool:
        """Register a Parquet dataset directly in DataFusion (preferred).

        This avoids materializing Parquet files into an in-memory Arrow table.
        Falls back to the legacy PyArrow read+concat path if unsupported.
        """
        register_parquet = getattr(self.ctx, "register_parquet", None)
        if not callable(register_parquet):
            return False

        try:
            if len(file_paths) == 1:
                register_parquet(table_name, file_paths[0])
                schema = self.ctx.table(table_name).schema()
                if len(schema) == 0:
                    try:
                        self.ctx.deregister_table(table_name)
                    except Exception:
                        pass
                    return False
                return True

            # DataFusion's Python binding does not reliably accept a list of file paths for
            # register_parquet(). Register each file separately and UNION them into a single
            # logical table for queries. This stays lazy/streaming and avoids materializing
            # Parquet into an in-memory Arrow table.
            temp_tables: list[str] = []
            for idx, file_path in enumerate(file_paths):
                temp_table = f"{table_name}__p{idx}"
                try:
                    self.ctx.deregister_table(temp_table)
                except Exception:
                    pass

                try:
                    register_parquet(temp_table, file_path)
                    temp_tables.append(temp_table)
                except Exception as e:
                    logger.warning(
                        "Skipping unreadable parquet file during registration",
                        extra={
                            "table": table_name,
                            "file_path": file_path,
                            "error": str(e),
                            "error_type": type(e).__name__,
                        },
                    )

            if not temp_tables:
                return False

            union_sql = " UNION ALL ".join([f"SELECT * FROM {t}" for t in temp_tables])
            df = self.ctx.sql(union_sql)
            self.ctx.register_table(table_name, df)
            schema = self.ctx.table(table_name).schema()
            if len(schema) == 0:
                try:
                    self.ctx.deregister_table(table_name)
                except Exception:
                    pass
                return False
            return True
        except Exception as e:
            logger.debug(
                "DataFusion register_parquet failed; will fall back to PyArrow read_table",
                extra={"table": table_name, "error": str(e), "error_type": type(e).__name__},
            )
            return False

    def register_cold(self, file_paths: list[str]) -> None:
        """Register COLD tier Parquet files as 'cold_spans' table.

        Cold tier contains data from WAL flushes and is selected via the SQLite
        metadata index (trace/service → file paths).
        Corrupt files are skipped gracefully.

        Args:
            file_paths: List of Parquet file paths from SQLite metadata
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

            valid_file_paths = self._filter_nonempty_parquet_files(
                file_paths, table_name="cold_spans"
            )
            if not valid_file_paths:
                self._cold_registered = False
                logger.debug(
                    "No usable cold Parquet files to register",
                    extra={"candidate_files": len(file_paths)},
                )
                return

            # Prefer DataFusion-native Parquet registration (lazy / streaming).
            if self._try_register_parquet("cold_spans", valid_file_paths):
                self._cold_registered = True
                logger.debug(
                    "Registered COLD tier files (parquet scan)",
                    extra={"file_count": len(valid_file_paths)},
                )
                return

            # Legacy fallback: Try batch read first (faster), fall back to individual reads
            # if a corrupt file is present. This path materializes Parquet into memory.
            file_count = len(valid_file_paths)
            try:
                arrow_table = pq.read_table(valid_file_paths)
            except Exception:
                # Batch read failed - read individually to skip corrupt files
                valid_tables = []
                for file_path in valid_file_paths:
                    try:
                        table = pq.read_table(file_path)
                        valid_tables.append(table)
                    except Exception as e:
                        logger.warning(f"Skipping corrupt cold file: {file_path} - {e}")
                        continue

                if not valid_tables:
                    self._cold_registered = False
                    logger.debug("No valid cold Parquet files found")
                    return

                file_count = len(valid_tables)
                arrow_table = pa.concat_tables(valid_tables)

            df = self.ctx.from_arrow(arrow_table)
            self.ctx.register_table("cold_spans", df)
            self._cold_registered = True

            logger.debug(
                "Registered COLD tier files",
                extra={"file_count": file_count, "row_count": arrow_table.num_rows},
            )

        except Exception as e:
            logger.error(f"Failed to register cold files: {e}")
            self._cold_registered = False

    def register_hot(self, snapshot_path: str | None) -> None:
        """Register HOT tier Parquet snapshot as 'hot_spans' table.

        Hot tier contains unflushed WAL data from Rust ingestion service.
        The backend calls PrepareHotSnapshot RPC to get a stable Parquet file path.

        Args:
            snapshot_path: Path to hot snapshot Parquet file, or None if unavailable
        """
        try:
            try:
                self.ctx.deregister_table("hot_spans")
            except Exception:
                pass

            if not snapshot_path:
                self._hot_registered = False
                logger.debug("No hot snapshot path provided, skipping HOT tier")
                return

            valid_snapshot = self._filter_nonempty_parquet_files(
                [snapshot_path], table_name="hot_spans"
            )
            if not valid_snapshot:
                self._hot_registered = False
                logger.debug(
                    "Hot snapshot is not usable, skipping HOT tier", extra={"path": snapshot_path}
                )
                return

            # Prefer DataFusion-native Parquet registration (lazy / streaming).
            if self._try_register_parquet("hot_spans", valid_snapshot):
                self._hot_registered = True
                logger.debug(
                    "Registered HOT tier snapshot (parquet scan)",
                    extra={"path": snapshot_path},
                )
                return

            # Legacy fallback: materialize snapshot into memory.
            try:
                arrow_table = pq.read_table(snapshot_path)
            except Exception as e:
                self._hot_registered = False
                logger.warning(f"Failed to read hot snapshot: {snapshot_path} - {e}")
                return

            if arrow_table.num_rows == 0:
                self._hot_registered = False
                logger.debug("HOT snapshot is empty, skipping registration")
                return

            df = self.ctx.from_arrow(arrow_table)
            self.ctx.register_table("hot_spans", df)
            self._hot_registered = True

            logger.debug(
                "Registered HOT tier snapshot",
                extra={"path": snapshot_path, "row_count": arrow_table.num_rows},
            )

        except Exception as e:
            logger.error(f"Failed to register hot snapshot: {e}")
            self._hot_registered = False

    def query_distinct_service_names(self) -> list[str]:
        """Get distinct service names across both tiers.

        Uses UNION to deduplicate service names automatically.

        Returns:
            Sorted list of unique service names
        """
        sources = []
        if self._cold_registered:
            sources.append("SELECT DISTINCT service_name FROM cold_spans")
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

    def query_spans_two_tier(
        self,
        *,
        trace_id: str | None = None,
        service_name: str | None = None,
        root_only: bool = False,
        workflow_only: bool = False,
        order_by: str = "start_time DESC",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Query unified spans across both tiers with deduplication.

        Priority: Cold > Hot (same (trace_id, span_id), Cold wins).

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
        if not self._cold_registered and not self._hot_registered:
            logger.debug("No data sources registered for two-tier query")
            return []

        def _escape_sql_literal(value: str) -> str:
            # Defensive escaping for DataFusion SQL string literals.
            return value.replace("'", "''")

        # Build WHERE clauses
        where_clauses: list[str] = []
        if trace_id:
            where_clauses.append(f"trace_id = '{_escape_sql_literal(trace_id)}'")
        if service_name:
            where_clauses.append(f"service_name = '{_escape_sql_literal(service_name)}'")
        if root_only:
            where_clauses.append("(parent_span_id IS NULL OR parent_span_id = '')")
        if workflow_only:
            # Workflow spans are identified via a JSON attribute (junjo.span_type=workflow).
            #
            # IMPORTANT: Apply this filter *in SQL* so that LIMIT applies to workflow spans
            # (workflow executions) rather than to arbitrary spans and then post-filtering
            # in Python (which can yield only 1–3 workflows even when lots exist).
            #
            # Ingestion serializes attributes via serde_json::to_string() (compact JSON),
            # so a substring match is stable and avoids needing JSON functions in DataFusion.
            where_clauses.append('attributes LIKE \'%"junjo.span_type":"workflow"%\'')

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        sql = self._build_two_tier_query(where_sql, order_by, limit)

        logger.debug(f"Two-tier SQL: {sql[:500]}...")

        try:
            df = self.ctx.sql(sql)
            batches = df.collect()

            rows = self._convert_batches_to_api_format(batches)

            # Defensive post-filter to ensure correctness if any non-standard JSON
            # serialization makes it through the SQL LIKE filter.
            if workflow_only:
                rows = [
                    r
                    for r in rows
                    if r.get("attributes_json", {}).get("junjo.span_type") == "workflow"
                ]

            return rows

        except Exception as e:
            logger.error(f"Two-tier query failed: {e}")
            raise

    def _build_two_tier_query(self, where_sql: str, order_by: str, limit: int | None) -> str:
        """Build SQL that merges both tiers with deduplication."""
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

        if self._hot_registered:
            tier_queries.append(f"""
                SELECT {select_cols}, 'hot' as _tier
                FROM hot_spans
                WHERE {where_sql}
            """)

        if not tier_queries:
            return "SELECT 1 WHERE 1=0"  # Empty result

        # If only one tier, no need for deduplication
        if len(tier_queries) == 1:
            base_select = select_cols.replace(
                "CAST(start_time AS BIGINT) as start_time_ns", "start_time_ns"
            )
            base_select = base_select.replace(
                "CAST(end_time AS BIGINT) as end_time_ns", "end_time_ns"
            )

            if self._cold_registered:
                table_name = "cold_spans"
            else:
                table_name = "hot_spans"

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
            WHERE {where_sql}
            ORDER BY {order_by.replace("start_time", "start_time_ns")}
            """

            if limit:
                sql += f" LIMIT {limit}"

            return sql

        union_sql = " UNION ALL ".join(tier_queries)

        # Deduplicate: cold > hot priority
        sql = f"""
        WITH combined AS ({union_sql}),
        ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY trace_id, span_id
                    ORDER BY CASE _tier
                        WHEN 'cold' THEN 0
                        ELSE 1
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
