"""In-memory tracker for recently flushed Parquet files.

This exists to close a visibility gap between:
1) ingestion flushes a new Parquet file (COLD tier)
2) backend background indexer extracts metadata into SQLite (trace->file mappings)

During that window, queries that rely on SQLite metadata may not "see" the new
file yet, and the WAL may already be empty (so HOT snapshot is empty). If a user
clicks a very new workflow execution in this gap, the UI can show "No logs found."

We track recently flushed Parquet paths (via NotifyNewParquetFile) and temporarily
include them as additional "cold" sources for DataFusion queries until indexing
completes or the entry expires.
"""

from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_recent_files: dict[str, float] = {}


def record_new_parquet_file(file_path: str) -> None:
    """Record a newly flushed Parquet file path."""
    now = time.monotonic()
    with _lock:
        _recent_files[file_path] = now


def mark_parquet_file_indexed(file_path: str) -> None:
    """Remove a Parquet file from the 'recent' set after indexing completes."""
    with _lock:
        _recent_files.pop(file_path, None)


def get_recent_parquet_files(*, max_age_seconds: float = 120.0, limit: int = 10) -> list[str]:
    """Return recently flushed (and potentially unindexed) Parquet files.

    Args:
        max_age_seconds: Maximum age to keep entries.
        limit: Maximum number of paths to return (most recent first).

    Returns:
        List of file paths ordered by most recent first.
    """
    now = time.monotonic()
    with _lock:
        expired = [p for p, t in _recent_files.items() if (now - t) > max_age_seconds]
        for path in expired:
            _recent_files.pop(path, None)

        items = sorted(_recent_files.items(), key=lambda kv: kv[1], reverse=True)
        return [path for path, _ts in items[:limit]]
