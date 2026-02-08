"""SQLite metadata maintenance operations.

Cleanup, retention, and filesystem sync for the metadata index.

Operations:
- Time-based retention (delete files older than N days)
- Filesystem sync (reconcile index with actual files)
- Full rebuild (regenerate index from Parquet files)
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from loguru import logger

from app.db_sqlite.metadata.db import get_connection
from app.features.parquet_indexer.file_scanner import scan_parquet_files


def cleanup_old_files(days: int) -> int:
    """Remove files older than N days from the index.

    Uses CASCADE delete to automatically clean up:
    - trace_files
    - file_services
    - workflow_files

    Note: llm_traces does not have FK, requires separate cleanup.

    Args:
        days: Number of days to retain

    Returns:
        Number of files deleted
    """
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    cutoff_str = cutoff.isoformat()

    conn = get_connection()

    # Get trace_ids that will be orphaned (for llm_traces cleanup)
    orphaned_traces = conn.execute(
        """
        SELECT DISTINCT tf.trace_id
        FROM trace_files tf
        JOIN parquet_files pf ON tf.file_id = pf.file_id
        WHERE pf.max_time < ?
        """,
        [cutoff_str],
    ).fetchall()
    orphaned_trace_ids = {row[0] for row in orphaned_traces}

    # Delete old files (CASCADE handles trace_files, file_services, workflow_files)
    cursor = conn.execute(
        "DELETE FROM parquet_files WHERE max_time < ?",
        [cutoff_str],
    )
    deleted_count = cursor.rowcount

    # Clean up llm_traces for orphaned trace_ids
    if orphaned_trace_ids:
        # Need to check if trace still exists in any remaining file
        for trace_id in orphaned_trace_ids:
            remaining = conn.execute(
                "SELECT 1 FROM trace_files WHERE trace_id = ? LIMIT 1",
                [trace_id],
            ).fetchone()
            if not remaining:
                conn.execute(
                    "DELETE FROM llm_traces WHERE trace_id = ?",
                    [trace_id],
                )

    conn.commit()

    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} old files from metadata index")

    return deleted_count


def sync_with_filesystem(parquet_dir: str) -> dict:
    """Synchronize index with filesystem.

    On startup, ensures index matches actual files:
    1. Remove entries for deleted files
    2. Identify files needing indexing

    Args:
        parquet_dir: Path to Parquet storage directory

    Returns:
        Dict with 'removed' (count) and 'missing' (list of paths)
    """
    conn = get_connection()
    parquet_path = Path(parquet_dir)

    if not parquet_path.exists():
        logger.warning(
            "Parquet storage path does not exist; skipping metadata filesystem sync",
            extra={"parquet_dir": parquet_dir},
        )
        return {"removed": 0, "missing": []}

    if not parquet_path.is_dir():
        logger.warning(
            "Parquet storage path is not a directory; skipping metadata filesystem sync",
            extra={"parquet_dir": parquet_dir},
        )
        return {"removed": 0, "missing": []}

    # Get all indexed paths
    indexed_paths = conn.execute("SELECT file_path FROM parquet_files").fetchall()
    indexed_set = {row[0] for row in indexed_paths}

    # Get all actual files
    file_infos = scan_parquet_files(str(parquet_path))
    actual_files = {f.path for f in file_infos}

    # Find orphaned index entries (file deleted from disk)
    orphaned = indexed_set - actual_files
    removed_count = 0
    for path in orphaned:
        conn.execute("DELETE FROM parquet_files WHERE file_path = ?", [path])
        removed_count += 1

    if removed_count > 0:
        conn.commit()
        logger.info(f"Removed {removed_count} orphaned entries from metadata index")

    # Find files needing indexing
    missing = list(actual_files - indexed_set)

    return {
        "removed": removed_count,
        "missing": missing,
    }


def rebuild_from_scratch() -> None:
    """Clear all tables for a full rebuild.

    After calling this, re-index all Parquet files.
    Useful for schema migrations or corruption recovery.
    """
    conn = get_connection()

    # Clear in order respecting FK constraints
    conn.execute("DELETE FROM llm_traces")
    conn.execute("DELETE FROM workflow_files")
    conn.execute("DELETE FROM file_services")
    conn.execute("DELETE FROM trace_files")
    conn.execute("DELETE FROM parquet_files")
    conn.execute("DELETE FROM failed_parquet_files")

    conn.commit()

    # Reclaim space (VACUUM must run outside a transaction)
    conn.execute("VACUUM")
    conn.commit()
    logger.info("Metadata index cleared for rebuild")


def vacuum() -> None:
    """Reclaim unused space in the database.

    Should be called after large deletes.
    """
    conn = get_connection()
    conn.commit()
    conn.execute("VACUUM")
    conn.commit()
    logger.debug("Metadata database vacuumed")


def get_index_stats() -> dict:
    """Get statistics about the metadata index.

    Returns:
        Dict with table counts and size estimates
    """
    conn = get_connection()

    stats = {
        "parquet_files": conn.execute("SELECT COUNT(*) FROM parquet_files").fetchone()[0],
        "trace_files": conn.execute("SELECT COUNT(*) FROM trace_files").fetchone()[0],
        "file_services": conn.execute("SELECT COUNT(*) FROM file_services").fetchone()[0],
        "llm_traces": conn.execute("SELECT COUNT(*) FROM llm_traces").fetchone()[0],
        "workflow_files": conn.execute("SELECT COUNT(*) FROM workflow_files").fetchone()[0],
        "failed_files": conn.execute("SELECT COUNT(*) FROM failed_parquet_files").fetchone()[0],
    }

    # Estimate unique traces
    stats["unique_traces"] = conn.execute(
        "SELECT COUNT(DISTINCT trace_id) FROM trace_files"
    ).fetchone()[0]

    # Estimate unique services
    stats["unique_services"] = conn.execute(
        "SELECT COUNT(DISTINCT service_name) FROM file_services"
    ).fetchone()[0]

    return stats
