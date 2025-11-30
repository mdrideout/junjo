"""V4 DuckDB Repository for Parquet file and span metadata operations.

This repository handles all DuckDB operations for the V4 architecture:
- parquet_files: Registry of indexed Parquet files
- span_metadata: Lightweight span data for listings
- services: Service catalog with aggregated stats
- failed_parquet_files: Tracking for files that failed to index
"""

from datetime import datetime

from loguru import logger

from app.db_duckdb.db_config import get_connection
from app.features.parquet_indexer.parquet_reader import ParquetFileData, SpanMetadata


def get_indexed_file_paths() -> set[str]:
    """Get all file paths already indexed in DuckDB.

    Used for deduplication during polling - only process files
    that haven't been indexed yet.

    Returns:
        Set of absolute file paths that are already in parquet_files table.
    """
    with get_connection() as conn:
        result = conn.execute("SELECT file_path FROM parquet_files").fetchall()
        return {row[0] for row in result}


def is_file_indexed(file_path: str) -> bool:
    """Check if a specific file has been indexed.

    Args:
        file_path: Absolute path to the Parquet file

    Returns:
        True if file is already in parquet_files table
    """
    with get_connection() as conn:
        result = conn.execute(
            "SELECT 1 FROM parquet_files WHERE file_path = ?", [file_path]
        ).fetchone()
        return result is not None


def register_parquet_file(file_data: ParquetFileData) -> int:
    """Register a Parquet file in the registry.

    Inserts the file metadata and returns the generated file_id.

    Args:
        file_data: Extracted file data from parquet_reader

    Returns:
        The generated file_id for use in span_metadata FK

    Raises:
        Exception: If insert fails (e.g., duplicate file_path)
    """
    with get_connection() as conn:
        # Use INSERT RETURNING to get the auto-generated file_id
        result = conn.execute(
            """
            INSERT INTO parquet_files (
                file_path, service_name, min_time, max_time,
                row_count, size_bytes
            ) VALUES (?, ?, ?, ?, ?, ?)
            RETURNING file_id
            """,
            [
                file_data.file_path,
                file_data.service_name,
                file_data.min_time,
                file_data.max_time,
                file_data.row_count,
                file_data.size_bytes,
            ],
        ).fetchone()

        if result is None:
            raise RuntimeError(f"Failed to get file_id after insert: {file_data.file_path}")

        file_id = result[0]
        logger.debug(f"Registered parquet file: {file_data.file_path} -> file_id={file_id}")
        return file_id


def batch_insert_span_metadata(file_id: int, spans: list[SpanMetadata]) -> int:
    """Insert span metadata rows in batch.

    Uses executemany for efficient bulk insert.

    Args:
        file_id: FK to parquet_files table
        spans: List of span metadata to insert

    Returns:
        Number of rows inserted
    """
    if not spans:
        return 0

    with get_connection() as conn:
        # Prepare rows for batch insert
        rows = [
            (
                span.span_id,
                span.trace_id,
                span.parent_span_id,
                span.service_name,
                span.name,
                span.start_time,
                span.end_time,
                span.duration_ns,
                span.status_code,
                span.span_kind,
                span.is_root,
                span.junjo_span_type,
                file_id,
            )
            for span in spans
        ]

        conn.executemany(
            """
            INSERT INTO span_metadata (
                span_id, trace_id, parent_span_id, service_name, name,
                start_time, end_time, duration_ns, status_code, span_kind,
                is_root, junjo_span_type, file_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

        logger.debug(f"Inserted {len(rows)} span metadata rows for file_id={file_id}")
        return len(rows)


def upsert_service(
    service_name: str, min_time: datetime, max_time: datetime, span_count: int
) -> None:
    """Update or insert service catalog entry.

    Updates first_seen/last_seen bounds and accumulates span count.

    Args:
        service_name: The service name
        min_time: Minimum time from the indexed file
        max_time: Maximum time from the indexed file
        span_count: Number of spans in the indexed file
    """
    with get_connection() as conn:
        # Try to update existing row
        result = conn.execute(
            """
            UPDATE services
            SET first_seen = LEAST(first_seen, ?),
                last_seen = GREATEST(last_seen, ?),
                total_spans = total_spans + ?
            WHERE service_name = ?
            RETURNING service_name
            """,
            [min_time, max_time, span_count, service_name],
        ).fetchone()

        if result is None:
            # Insert new service
            conn.execute(
                """
                INSERT INTO services (service_name, first_seen, last_seen, total_spans)
                VALUES (?, ?, ?, ?)
                """,
                [service_name, min_time, max_time, span_count],
            )
            logger.debug(f"Added new service: {service_name}")
        else:
            logger.debug(f"Updated service: {service_name} (+{span_count} spans)")


def index_parquet_file(file_data: ParquetFileData) -> int:
    """Index a complete Parquet file in a single transaction.

    This is the main entry point for the indexer. It:
    1. Registers the file in parquet_files
    2. Inserts all span metadata
    3. Updates the service catalog

    Args:
        file_data: Extracted file data from parquet_reader

    Returns:
        Number of spans indexed

    Raises:
        Exception: If any part of the indexing fails
    """
    with get_connection() as conn:
        try:
            conn.execute("BEGIN TRANSACTION")

            # 1. Register file
            result = conn.execute(
                """
                INSERT INTO parquet_files (
                    file_path, service_name, min_time, max_time,
                    row_count, size_bytes
                ) VALUES (?, ?, ?, ?, ?, ?)
                RETURNING file_id
                """,
                [
                    file_data.file_path,
                    file_data.service_name,
                    file_data.min_time,
                    file_data.max_time,
                    file_data.row_count,
                    file_data.size_bytes,
                ],
            ).fetchone()

            if result is None:
                raise RuntimeError("Failed to get file_id after insert")
            file_id = result[0]

            # 2. Insert span metadata
            rows = [
                (
                    span.span_id,
                    span.trace_id,
                    span.parent_span_id,
                    span.service_name,
                    span.name,
                    span.start_time,
                    span.end_time,
                    span.duration_ns,
                    span.status_code,
                    span.span_kind,
                    span.is_root,
                    span.junjo_span_type,
                    file_id,
                )
                for span in file_data.spans
            ]

            conn.executemany(
                """
                INSERT INTO span_metadata (
                    span_id, trace_id, parent_span_id, service_name, name,
                    start_time, end_time, duration_ns, status_code, span_kind,
                    is_root, junjo_span_type, file_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

            # 3. Update service catalog
            existing = conn.execute(
                "SELECT 1 FROM services WHERE service_name = ?",
                [file_data.service_name],
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE services
                    SET first_seen = LEAST(first_seen, ?),
                        last_seen = GREATEST(last_seen, ?),
                        total_spans = total_spans + ?
                    WHERE service_name = ?
                    """,
                    [
                        file_data.min_time,
                        file_data.max_time,
                        file_data.row_count,
                        file_data.service_name,
                    ],
                )
            else:
                conn.execute(
                    """
                    INSERT INTO services (service_name, first_seen, last_seen, total_spans)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        file_data.service_name,
                        file_data.min_time,
                        file_data.max_time,
                        file_data.row_count,
                    ],
                )

            conn.execute("COMMIT")

            logger.info(
                f"Indexed {file_data.row_count} spans from {file_data.file_path} "
                f"(file_id={file_id}, service={file_data.service_name})"
            )
            return file_data.row_count

        except Exception:
            conn.execute("ROLLBACK")
            raise


# ============================================================================
# Failed File Tracking
# ============================================================================


def get_failed_file_paths() -> set[str]:
    """Get all file paths that have failed to index.

    Used during polling to skip known bad files.

    Returns:
        Set of absolute file paths in failed_parquet_files table.
    """
    with get_connection() as conn:
        result = conn.execute("SELECT file_path FROM failed_parquet_files").fetchall()
        return {row[0] for row in result}


def record_failed_file(
    file_path: str,
    error_type: str,
    error_message: str,
    file_size: int | None = None,
) -> None:
    """Record a file that failed to index.

    If the file already exists in the table, increments retry_count
    and updates the error info and timestamp.

    Args:
        file_path: Absolute path to the failed file
        error_type: Exception class name (e.g., "ValueError", "ArrowInvalid")
        error_message: Full error message
        file_size: File size in bytes (optional)
    """
    with get_connection() as conn:
        # Check if already recorded
        existing = conn.execute(
            "SELECT retry_count FROM failed_parquet_files WHERE file_path = ?",
            [file_path],
        ).fetchone()

        if existing:
            # Update existing record
            conn.execute(
                """
                UPDATE failed_parquet_files
                SET error_type = ?,
                    error_message = ?,
                    file_size = ?,
                    failed_at = CURRENT_TIMESTAMP,
                    retry_count = retry_count + 1
                WHERE file_path = ?
                """,
                [error_type, error_message, file_size, file_path],
            )
            logger.debug(f"Updated failed file record: {file_path} (retry #{existing[0] + 1})")
        else:
            # Insert new record
            conn.execute(
                """
                INSERT INTO failed_parquet_files (
                    file_path, error_type, error_message, file_size
                ) VALUES (?, ?, ?, ?)
                """,
                [file_path, error_type, error_message, file_size],
            )
            logger.debug(f"Recorded failed file: {file_path}")


def get_failed_files() -> list[dict]:
    """Get all failed files for reporting/debugging.

    Returns:
        List of dicts with file_path, error_type, error_message,
        file_size, failed_at, retry_count.
    """
    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT file_path, error_type, error_message, file_size, failed_at, retry_count
            FROM failed_parquet_files
            ORDER BY failed_at DESC
            """
        ).fetchall()

        return [
            {
                "file_path": row[0],
                "error_type": row[1],
                "error_message": row[2],
                "file_size": row[3],
                "failed_at": row[4],
                "retry_count": row[5],
            }
            for row in result
        ]


def clear_failed_file(file_path: str) -> bool:
    """Remove a file from the failed list (e.g., after manual fix).

    Args:
        file_path: Absolute path to remove from failed list

    Returns:
        True if a record was deleted, False if not found
    """
    with get_connection() as conn:
        result = conn.execute(
            "DELETE FROM failed_parquet_files WHERE file_path = ? RETURNING file_path",
            [file_path],
        ).fetchone()
        return result is not None


# ============================================================================
# Query Functions for DataFusion
# ============================================================================
# These functions query DuckDB metadata to find which Parquet files
# need to be queried by DataFusion.


def get_file_paths_for_trace(trace_id: str) -> list[str]:
    """Get Parquet file paths that contain spans for a trace.

    Uses span_metadata to find file_ids, then joins to parquet_files
    for the actual file paths.

    Args:
        trace_id: The trace ID to look up

    Returns:
        List of Parquet file paths (may be empty if trace not found)
    """
    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT DISTINCT pf.file_path
            FROM span_metadata sm
            JOIN parquet_files pf ON sm.file_id = pf.file_id
            WHERE sm.trace_id = ?
            """,
            [trace_id],
        ).fetchall()
        return [row[0] for row in result]


def get_file_paths_for_span(span_id: str) -> list[str]:
    """Get Parquet file path(s) containing a specific span.

    Args:
        span_id: The span ID to look up

    Returns:
        List of Parquet file paths (typically 1, may be 0 if not found)
    """
    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT DISTINCT pf.file_path
            FROM span_metadata sm
            JOIN parquet_files pf ON sm.file_id = pf.file_id
            WHERE sm.span_id = ?
            """,
            [span_id],
        ).fetchall()
        return [row[0] for row in result]


def get_file_paths_for_service(
    service_name: str,
    limit: int | None = None,
    is_root: bool | None = None,
) -> list[str]:
    """Get Parquet file paths containing spans for a service.

    Args:
        service_name: The service name to filter by
        limit: Optional limit on spans (affects which files are returned)
        is_root: If True, only return files with root spans

    Returns:
        List of distinct Parquet file paths ordered by most recent first
    """
    with get_connection() as conn:
        # Build query based on filters
        sql = """
            SELECT DISTINCT pf.file_path
            FROM span_metadata sm
            JOIN parquet_files pf ON sm.file_id = pf.file_id
            WHERE sm.service_name = ?
        """
        params: list = [service_name]

        if is_root is True:
            sql += " AND sm.is_root = true"

        # Order by most recent file first
        sql += " ORDER BY pf.max_time DESC"

        if limit:
            # We need files that contain at least `limit` spans
            # For simplicity, we fetch enough files to likely contain that many spans
            # A more precise approach would require a subquery
            sql += f" LIMIT {min(limit, 100)}"

        result = conn.execute(sql, params).fetchall()
        return [row[0] for row in result]


def get_file_paths_for_time_range(
    start_time: datetime,
    end_time: datetime,
    service_name: str | None = None,
) -> list[str]:
    """Get Parquet file paths overlapping a time range.

    Uses parquet_files.min_time and max_time for efficient pruning.

    Args:
        start_time: Start of time range (inclusive)
        end_time: End of time range (inclusive)
        service_name: Optional service filter

    Returns:
        List of Parquet file paths that may contain spans in the range
    """
    with get_connection() as conn:
        sql = """
            SELECT file_path
            FROM parquet_files
            WHERE min_time <= ? AND max_time >= ?
        """
        params: list = [end_time, start_time]

        if service_name:
            sql += " AND service_name = ?"
            params.append(service_name)

        sql += " ORDER BY max_time DESC"

        result = conn.execute(sql, params).fetchall()
        return [row[0] for row in result]


def get_all_services() -> list[str]:
    """Get all service names from the services table.

    Returns:
        List of service names in alphabetical order
    """
    with get_connection() as conn:
        result = conn.execute("SELECT service_name FROM services ORDER BY service_name").fetchall()
        return [row[0] for row in result]


def get_root_span_metadata(service_name: str, limit: int = 500) -> list[dict]:
    """Get root span metadata for listing traces.

    Returns lightweight span info for UI listing without needing Parquet.

    Args:
        service_name: Service to filter by
        limit: Maximum spans to return

    Returns:
        List of span metadata dicts (not full spans - no attributes)
    """
    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT
                sm.span_id, sm.trace_id, sm.parent_span_id,
                sm.service_name, sm.name,
                sm.start_time, sm.end_time,
                sm.duration_ns, sm.status_code, sm.span_kind,
                sm.is_root, pf.file_path
            FROM span_metadata sm
            JOIN parquet_files pf ON sm.file_id = pf.file_id
            WHERE sm.service_name = ? AND sm.is_root = true
            ORDER BY sm.start_time DESC
            LIMIT ?
            """,
            [service_name, limit],
        ).fetchall()

        columns = [
            "span_id",
            "trace_id",
            "parent_span_id",
            "service_name",
            "name",
            "start_time",
            "end_time",
            "duration_ns",
            "status_code",
            "span_kind",
            "is_root",
            "file_path",
        ]
        return [dict(zip(columns, row)) for row in result]


def get_span_metadata_for_trace(trace_id: str) -> list[dict]:
    """Get all span metadata for a trace (for finding file paths).

    Args:
        trace_id: The trace ID

    Returns:
        List of span metadata dicts including file_path
    """
    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT
                sm.span_id, sm.trace_id, sm.parent_span_id,
                sm.service_name, sm.name,
                sm.start_time, sm.end_time,
                sm.duration_ns, sm.status_code, sm.span_kind,
                sm.is_root, pf.file_path
            FROM span_metadata sm
            JOIN parquet_files pf ON sm.file_id = pf.file_id
            WHERE sm.trace_id = ?
            ORDER BY sm.start_time DESC
            """,
            [trace_id],
        ).fetchall()

        columns = [
            "span_id",
            "trace_id",
            "parent_span_id",
            "service_name",
            "name",
            "start_time",
            "end_time",
            "duration_ns",
            "status_code",
            "span_kind",
            "is_root",
            "file_path",
        ]
        return [dict(zip(columns, row)) for row in result]


def get_file_paths_for_junjo_type(
    service_name: str, junjo_span_type: str, limit: int = 500
) -> list[str]:
    """Get Parquet file paths containing spans of a specific junjo type.

    Args:
        service_name: Service to filter by
        junjo_span_type: Type to filter by (workflow, subflow, node, run_concurrent)
        limit: Maximum results

    Returns:
        List of file paths ordered by most recent first
    """
    with get_connection() as conn:
        result = conn.execute(
            """
            SELECT DISTINCT pf.file_path
            FROM span_metadata sm
            JOIN parquet_files pf ON sm.file_id = pf.file_id
            WHERE sm.service_name = ? AND sm.junjo_span_type = ?
            ORDER BY pf.max_time DESC
            LIMIT ?
            """,
            [service_name, junjo_span_type, limit],
        ).fetchall()
        return [row[0] for row in result]
