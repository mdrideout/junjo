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
    add_llm_traces,
    add_service_mapping,
    add_trace_mappings,
    add_workflow_file,
    register_parquet_file,
)
from app.features.parquet_indexer.parquet_reader import ParquetFileData, SpanMetadata


def _span_is_llm(span: SpanMetadata) -> bool:
    """Return True if the span indicates an LLM operation.

    We support both:
    - OpenInference: openinference.span.kind == "LLM"
    - GenAI semconv: gen_ai.provider.name / gen_ai.operation.name present
    """
    if span.openinference_span_kind == "LLM":
        return True
    if span.gen_ai_provider_name:
        return True
    if span.gen_ai_operation_name:
        return True
    return False


def index_parquet_file(file_data: ParquetFileData) -> int:
    """Index a Parquet file into SQLite metadata index.

    Extracts per-trace metadata from the file data and inserts into
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

        # 2. Extract trace IDs (DISTINCT)
        trace_ids: set[str] = set()
        for span in file_data.spans:
            trace_ids.add(span.trace_id)

        add_trace_mappings(file_id, trace_ids)

        # 3. Extract service stats and add mappings
        service_stats: dict[str, dict] = {}
        for span in file_data.spans:
            svc = span.service_name
            if svc not in service_stats:
                service_stats[svc] = {
                    "min_time": span.start_time,
                    "max_time": span.end_time,
                    "count": 0,
                }
            stats = service_stats[svc]
            stats["min_time"] = min(stats["min_time"], span.start_time)
            stats["max_time"] = max(stats["max_time"], span.end_time)
            stats["count"] += 1

        for svc_name, stats in service_stats.items():
            add_service_mapping(
                file_id=file_id,
                service_name=svc_name,
                span_count=stats["count"],
                min_time=stats["min_time"],
                max_time=stats["max_time"],
            )

        # 4. Extract LLM trace IDs (traces containing LLM spans)
        llm_trace_ids: dict[str, set[str]] = {}  # service -> trace_ids
        for span in file_data.spans:
            if _span_is_llm(span):
                svc = span.service_name
                if svc not in llm_trace_ids:
                    llm_trace_ids[svc] = set()
                llm_trace_ids[svc].add(span.trace_id)

        for svc_name, tids in llm_trace_ids.items():
            add_llm_traces(svc_name, tids)

        # 5. Check for workflow spans
        has_workflow: dict[str, bool] = {}  # service -> has_workflow
        for span in file_data.spans:
            if span.junjo_span_type == "workflow":
                has_workflow[span.service_name] = True

        for svc_name in has_workflow:
            add_workflow_file(svc_name, file_id)

        # Commit transaction
        conn.commit()

        logger.info(
            f"SQLite indexed {file_data.row_count} spans from {file_data.file_path} "
            f"(file_id={file_id}, traces={len(trace_ids)}, services={len(service_stats)})"
        )

        return file_data.row_count

    except Exception:
        # Rollback on any error
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
