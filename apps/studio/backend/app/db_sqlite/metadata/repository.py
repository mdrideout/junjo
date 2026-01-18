"""SQLite metadata repository for Parquet file lookups.

Query functions for the metadata index. All operations are synchronous;
use asyncio.run_in_executor() for async contexts.

Key lookups:
- trace_id -> file_paths (which files contain a trace)
- service_name -> file_paths (which files contain a service)
- Semantic filters (LLM traces, workflow files)
"""

from datetime import datetime

from loguru import logger

from app.db_sqlite.metadata.db import get_connection

# ============================================================================
# File Registration (Write Operations)
# ============================================================================


def register_parquet_file(
    file_path: str,
    min_time: datetime,
    max_time: datetime,
    row_count: int,
    size_bytes: int,
) -> int:
    """Register a Parquet file in the index.

    Args:
        file_path: Absolute path to the Parquet file
        min_time: Earliest span timestamp in file
        max_time: Latest span timestamp in file
        row_count: Number of spans in file
        size_bytes: File size in bytes

    Returns:
        Generated file_id

    Raises:
        sqlite3.IntegrityError: If file already registered
    """
    conn = get_connection()
    cursor = conn.execute(
        """
        INSERT INTO parquet_files (file_path, min_time, max_time, row_count, size_bytes)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            file_path,
            min_time.isoformat(),
            max_time.isoformat(),
            row_count,
            size_bytes,
        ],
    )
    file_id = cursor.lastrowid
    if file_id is None:
        raise RuntimeError(f"Failed to get file_id after insert: {file_path}")

    return file_id


def add_trace_mappings(file_id: int, trace_ids: set[str]) -> int:
    """Add trace -> file mappings.

    Args:
        file_id: The file_id from parquet_files
        trace_ids: Set of trace IDs in this file

    Returns:
        Number of mappings added
    """
    if not trace_ids:
        return 0

    conn = get_connection()
    rows = [(trace_id, file_id) for trace_id in trace_ids]
    conn.executemany(
        "INSERT OR IGNORE INTO trace_files (trace_id, file_id) VALUES (?, ?)",
        rows,
    )
    return len(rows)


def add_service_mapping(
    file_id: int,
    service_name: str,
    span_count: int,
    min_time: datetime,
    max_time: datetime,
) -> None:
    """Add a service -> file mapping.

    Args:
        file_id: The file_id from parquet_files
        service_name: Service name
        span_count: Number of spans for this service in this file
        min_time: Earliest span time for this service
        max_time: Latest span time for this service
    """
    conn = get_connection()
    conn.execute(
        """
        INSERT OR REPLACE INTO file_services (file_id, service_name, span_count, min_time, max_time)
        VALUES (?, ?, ?, ?, ?)
        """,
        [file_id, service_name, span_count, min_time.isoformat(), max_time.isoformat()],
    )


def add_llm_traces(service_name: str, trace_ids: set[str]) -> int:
    """Record traces that contain LLM spans.

    Args:
        service_name: Service name
        trace_ids: Trace IDs with LLM spans

    Returns:
        Number of records added
    """
    if not trace_ids:
        return 0

    conn = get_connection()
    rows = [(service_name, trace_id) for trace_id in trace_ids]
    conn.executemany(
        "INSERT OR IGNORE INTO llm_traces (service_name, trace_id) VALUES (?, ?)",
        rows,
    )
    return len(rows)


def add_workflow_file(service_name: str, file_id: int) -> None:
    """Record that a file contains workflow spans.

    Args:
        service_name: Service name
        file_id: The file_id from parquet_files
    """
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO workflow_files (service_name, file_id) VALUES (?, ?)",
        [service_name, file_id],
    )


def record_failed_file(
    file_path: str,
    error_type: str,
    error_message: str,
    file_size: int | None = None,
) -> None:
    """Record a file that failed to index.

    If the file already exists, increments retry_count and updates error info.

    Args:
        file_path: Absolute path to the failed file
        error_type: Exception class name
        error_message: Full error message
        file_size: File size in bytes (optional)
    """
    conn = get_connection()

    # Check if already recorded
    existing = conn.execute(
        "SELECT retry_count FROM failed_parquet_files WHERE file_path = ?",
        [file_path],
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE failed_parquet_files
            SET error_type = ?,
                error_message = ?,
                file_size = ?,
                failed_at = datetime('now'),
                retry_count = retry_count + 1
            WHERE file_path = ?
            """,
            [error_type, error_message, file_size, file_path],
        )
        logger.debug(f"Updated failed file record: {file_path} (retry #{existing[0] + 1})")
    else:
        conn.execute(
            """
            INSERT INTO failed_parquet_files (file_path, error_type, error_message, file_size)
            VALUES (?, ?, ?, ?)
            """,
            [file_path, error_type, error_message, file_size],
        )
        logger.debug(f"Recorded failed file: {file_path}")

    conn.commit()


# ============================================================================
# Deduplication Queries (for background indexer)
# ============================================================================


def get_indexed_file_paths() -> set[str]:
    """Get all file paths already indexed.

    Used for deduplication during polling.

    Returns:
        Set of absolute file paths in parquet_files table.
    """
    conn = get_connection()
    result = conn.execute("SELECT file_path FROM parquet_files").fetchall()
    return {row[0] for row in result}


def get_failed_file_paths() -> set[str]:
    """Get all file paths that have failed to index.

    Used during polling to skip known bad files.

    Returns:
        Set of absolute file paths in failed_parquet_files table.
    """
    conn = get_connection()
    result = conn.execute("SELECT file_path FROM failed_parquet_files").fetchall()
    return {row[0] for row in result}


def is_file_indexed(file_path: str) -> bool:
    """Check if a specific file has been indexed.

    Args:
        file_path: Absolute path to the Parquet file

    Returns:
        True if file is already in parquet_files table
    """
    conn = get_connection()
    result = conn.execute(
        "SELECT 1 FROM parquet_files WHERE file_path = ?",
        [file_path],
    ).fetchone()
    return result is not None


# ============================================================================
# Query Functions (Read Operations)
# ============================================================================


def get_file_paths_for_trace(trace_id: str) -> list[str]:
    """Get Parquet file paths that contain spans for a trace.

    This is the critical lookup - O(log n) with B-tree index.

    Args:
        trace_id: The trace ID to look up

    Returns:
        List of Parquet file paths (may be empty if trace not found)
    """
    conn = get_connection()
    result = conn.execute(
        """
        SELECT pf.file_path
        FROM trace_files tf
        JOIN parquet_files pf ON tf.file_id = pf.file_id
        WHERE tf.trace_id = ?
        """,
        [trace_id],
    ).fetchall()
    return [row[0] for row in result]


def get_file_paths_for_service(
    service_name: str,
    limit: int | None = None,
) -> list[str]:
    """Get Parquet file paths containing spans for a service.

    Args:
        service_name: The service name to filter by
        limit: Optional limit on files returned

    Returns:
        List of distinct Parquet file paths ordered by most recent first
    """
    conn = get_connection()
    sql = """
        SELECT pf.file_path
        FROM file_services fs
        JOIN parquet_files pf ON fs.file_id = pf.file_id
        WHERE fs.service_name = ?
        ORDER BY pf.max_time DESC
    """
    params: list = [service_name]

    if limit:
        sql += " LIMIT ?"
        params.append(limit)

    result = conn.execute(sql, params).fetchall()
    return [row[0] for row in result]


def get_services() -> list[str]:
    """Get all distinct service names.

    Returns:
        List of service names in alphabetical order.
    """
    conn = get_connection()
    result = conn.execute(
        "SELECT DISTINCT service_name FROM file_services ORDER BY service_name"
    ).fetchall()
    return [row[0] for row in result]


def get_llm_trace_ids(service_name: str, limit: int = 500) -> set[str]:
    """Get trace IDs that contain at least one LLM span.

    Args:
        service_name: Service to filter by
        limit: Maximum traces to return

    Returns:
        Set of trace IDs that have LLM spans
    """
    conn = get_connection()
    result = conn.execute(
        """
        SELECT trace_id
        FROM llm_traces
        WHERE service_name = ?
        LIMIT ?
        """,
        [service_name, limit],
    ).fetchall()
    return {row[0] for row in result}


def get_workflow_file_paths(service_name: str, limit: int = 500) -> list[str]:
    """Get Parquet file paths containing workflow spans.

    Args:
        service_name: Service to filter by
        limit: Maximum files to return

    Returns:
        List of file paths ordered by most recent first
    """
    conn = get_connection()
    result = conn.execute(
        """
        SELECT pf.file_path
        FROM workflow_files wf
        JOIN parquet_files pf ON wf.file_id = pf.file_id
        WHERE wf.service_name = ?
        ORDER BY pf.max_time DESC
        LIMIT ?
        """,
        [service_name, limit],
    ).fetchall()
    return [row[0] for row in result]


def get_all_parquet_file_paths() -> list[str]:
    """Get all indexed Parquet file paths.

    Used for two-tier queries where we need all cold files.

    Returns:
        List of all indexed Parquet file paths ordered by most recent first
    """
    conn = get_connection()
    result = conn.execute("SELECT file_path FROM parquet_files ORDER BY max_time DESC").fetchall()
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
    conn = get_connection()

    if service_name:
        result = conn.execute(
            """
            SELECT pf.file_path
            FROM parquet_files pf
            JOIN file_services fs ON pf.file_id = fs.file_id
            WHERE pf.min_time <= ? AND pf.max_time >= ?
              AND fs.service_name = ?
            ORDER BY pf.max_time DESC
            """,
            [end_time.isoformat(), start_time.isoformat(), service_name],
        ).fetchall()
    else:
        result = conn.execute(
            """
            SELECT file_path
            FROM parquet_files
            WHERE min_time <= ? AND max_time >= ?
            ORDER BY max_time DESC
            """,
            [end_time.isoformat(), start_time.isoformat()],
        ).fetchall()

    return [row[0] for row in result]
