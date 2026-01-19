"""SQLite metadata index for Parquet files.

This module provides a lightweight index for Parquet file metadata,
replacing DuckDB's per-span indexing with per-trace indexing.

Key benefits:
- 10-20x memory reduction (15-30MB vs 200-300MB)
- Bounded memory regardless of span count
- Uses stdlib sqlite3 (no C extension)
- Already in stack for user auth data

The index maps:
- trace_id -> file_paths (for trace queries)
- service_name -> file_paths (for service queries)
- Semantic filters (LLM traces, workflow files)

DataFusion continues to handle actual Parquet queries.
"""

from app.db_sqlite.metadata.db import (
    checkpoint_wal,
    get_connection,
    init_metadata_db,
)
from app.db_sqlite.metadata.indexer import index_parquet_file
from app.db_sqlite.metadata.maintenance import (
    cleanup_old_files,
    get_index_stats,
    rebuild_from_scratch,
    sync_with_filesystem,
    vacuum,
)
from app.db_sqlite.metadata.repository import (
    filter_llm_trace_ids,
    get_all_parquet_file_paths,
    get_failed_file_paths,
    get_file_paths_for_service,
    get_file_paths_for_trace,
    get_indexed_file_paths,
    get_llm_trace_ids,
    get_services,
    get_workflow_file_paths,
    is_file_indexed,
    record_failed_file,
)

__all__ = [
    # Database
    "init_metadata_db",
    "get_connection",
    "checkpoint_wal",
    # Indexer
    "index_parquet_file",
    # Repository - writes
    "record_failed_file",
    # Repository - reads
    "get_indexed_file_paths",
    "get_failed_file_paths",
    "is_file_indexed",
    "get_file_paths_for_trace",
    "get_file_paths_for_service",
    "get_services",
    "get_llm_trace_ids",
    "filter_llm_trace_ids",
    "get_workflow_file_paths",
    "get_all_parquet_file_paths",
    # Maintenance
    "cleanup_old_files",
    "sync_with_filesystem",
    "rebuild_from_scratch",
    "vacuum",
    "get_index_stats",
]
