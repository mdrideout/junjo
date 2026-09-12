"""Extract file/trace selection metadata without materializing per-span records.

Full span data stays in Parquet. The reader returns only the summaries needed
by the SQLite metadata index.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger


def nanoseconds_to_datetime(ns: int) -> datetime:
    """Convert nanoseconds to UTC datetime, flooring to microsecond precision."""
    seconds, remaining_ns = divmod(ns, 1_000_000_000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=remaining_ns // 1000)


@dataclass
class ServiceMetadata:
    """Service bounds stay in nanoseconds until the SQLite write boundary."""

    span_count: int
    min_time_ns: int
    max_time_ns: int


@dataclass
class ParquetFileData:
    """File and trace summaries used to select cold Parquet files."""

    file_path: str
    service_name: str
    min_time: datetime
    max_time: datetime
    row_count: int
    size_bytes: int
    trace_ids: set[str]
    services: dict[str, ServiceMetadata]
    llm_trace_ids: dict[str, set[str]]
    workflow_services: set[str]
    agent_services: set[str]


METADATA_COLUMNS = ["trace_id", "service_name", "start_time", "end_time", "attributes"]


def read_parquet_metadata(file_path: str, size_bytes: int) -> ParquetFileData:
    """Read and summarize the columns needed for SQLite file selection.

    Timestamp comparisons use integer nanoseconds. Only aggregate bounds need
    Python datetimes; no span payload or per-span metadata object is retained.
    """
    table = pq.read_table(file_path, columns=METADATA_COLUMNS)
    if table.num_rows == 0:
        raise ValueError(f"Empty Parquet file: {file_path}")

    trace_ids: set[str] = set()
    services: dict[str, ServiceMetadata] = {}
    llm_trace_ids: dict[str, set[str]] = {}
    workflow_services: set[str] = set()
    agent_services: set[str] = set()

    columns = (
        table.column("trace_id").to_pylist(),
        table.column("service_name").to_pylist(),
        table.column("start_time").cast(pa.int64()).to_pylist(),
        table.column("end_time").cast(pa.int64()).to_pylist(),
        table.column("attributes").to_pylist(),
    )
    for trace_id, service, start_ns, end_ns, attrs_str in zip(*columns, strict=True):
        trace_ids.add(trace_id)
        stats = services.get(service)
        if stats is None:
            services[service] = ServiceMetadata(1, start_ns, end_ns)
        else:
            stats.span_count += 1
            if start_ns < stats.min_time_ns:
                stats.min_time_ns = start_ns
            if end_ns > stats.max_time_ns:
                stats.max_time_ns = end_ns

        if attrs_str:
            try:
                attrs = json.loads(attrs_str) if isinstance(attrs_str, str) else attrs_str
                if (
                    attrs.get("openinference.span.kind") == "LLM"
                    or attrs.get("gen_ai.provider.name")
                    or attrs.get("gen_ai.operation.name")
                ):
                    traces = llm_trace_ids.get(service)
                    if traces is None:
                        traces = llm_trace_ids[service] = set()
                    traces.add(trace_id)
                if attrs.get("junjo.span_type") == "workflow":
                    workflow_services.add(service)
                if attrs.get("junjo.span_type") == "agent":
                    agent_services.add(service)
            except (json.JSONDecodeError, TypeError):
                pass

    min_time = nanoseconds_to_datetime(min(s.min_time_ns for s in services.values()))
    max_time = nanoseconds_to_datetime(max(s.max_time_ns for s in services.values()))
    service_name = next(iter(services))
    logger.debug(
        f"Read {table.num_rows} spans from {file_path}, "
        f"service={service_name}, time_range=[{min_time}, {max_time}]"
    )
    return ParquetFileData(
        file_path=file_path,
        service_name=service_name,
        min_time=min_time,
        max_time=max_time,
        row_count=table.num_rows,
        size_bytes=size_bytes,
        trace_ids=trace_ids,
        services=services,
        llm_trace_ids=llm_trace_ids,
        workflow_services=workflow_services,
        agent_services=agent_services,
    )
