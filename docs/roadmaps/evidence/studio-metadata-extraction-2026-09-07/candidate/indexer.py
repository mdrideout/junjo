"""SQLite metadata indexer for Parquet files.

Indexes Parquet file metadata into SQLite with per-trace granularity.
This replaces legacy per-span indexing with 50-100x less memory.

Key extraction:
- DISTINCT trace_id -> trace_files
- DISTINCT service_name -> file_services
- LLM spans (OpenInference or GenAI semantic conventions) -> llm_traces
- Workflow spans (junjo.span_type = 'workflow') -> workflow_files
"""

from loguru import logger

from app.db_sqlite.metadata.db import get_connection
from app.db_sqlite.metadata.repository import (
    add_agent_file,
    add_llm_traces,
    add_service_mapping,
    add_trace_mappings,
    add_workflow_file,
    register_parquet_file,
)
from app.features.parquet_indexer.parquet_reader import ParquetFileData, nanoseconds_to_datetime


def index_parquet_file(file_data: ParquetFileData) -> int:
    """Index a Parquet file into SQLite metadata index.

    Inserts the extracted file/trace summaries into
    SQLite in a single atomic transaction.

    Args:
        file_data: Extracted file data from parquet_reader

    Returns:
        Number of spans in the file (for logging consistency)

    Raises:
        Exception: If any part of the indexing fails (transaction rolled back)
    """
    conn = get_connection()

    try:
        # Begin explicit transaction
        conn.execute("BEGIN IMMEDIATE")

        # 1. Register the file
        file_id = register_parquet_file(
            file_path=file_data.file_path,
            min_time=file_data.min_time,
            max_time=file_data.max_time,
            row_count=file_data.row_count,
            size_bytes=file_data.size_bytes,
        )

        add_trace_mappings(file_id, file_data.trace_ids)

        for service, stats in file_data.services.items():
            add_service_mapping(
                file_id=file_id,
                service_name=service,
                span_count=stats.span_count,
                min_time=nanoseconds_to_datetime(stats.min_time_ns),
                max_time=nanoseconds_to_datetime(stats.max_time_ns),
            )

        for service, trace_ids in file_data.llm_trace_ids.items():
            add_llm_traces(service, trace_ids)

        for service in file_data.workflow_services:
            add_workflow_file(service, file_id)

        for service in file_data.agent_services:
            add_agent_file(service, file_id)

        # Commit transaction
        conn.commit()

        logger.info(
            f"SQLite indexed {file_data.row_count} spans from {file_data.file_path} "
            f"(file_id={file_id}, traces={len(file_data.trace_ids)}, services={len(file_data.services)})"
        )

        return file_data.row_count

    except Exception:
        # Rollback on any error
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
