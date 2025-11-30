"""Parquet file reader for span metadata extraction.

Reads Parquet files written by Go ingestion and extracts
span metadata columns for DuckDB indexing.

Note: This module only reads metadata columns needed for listings.
Full span data (attributes, events, resource_attributes) stays in Parquet.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger


def _timestamp_to_datetime(ts: pa.TimestampScalar | int) -> datetime:
    """Convert Arrow timestamp (nanoseconds) to Python datetime.

    PyArrow nanosecond timestamps can't be directly converted to datetime
    (which only supports microseconds). We convert via integer value.

    Args:
        ts: Arrow timestamp scalar or integer nanoseconds

    Returns:
        datetime with UTC timezone
    """
    if hasattr(ts, "value"):
        # Arrow scalar - get nanosecond value
        ns = ts.value
    else:
        # Already an int
        ns = ts

    # Convert nanoseconds to seconds + microseconds
    seconds = ns // 1_000_000_000
    remaining_ns = ns % 1_000_000_000
    microseconds = remaining_ns // 1000

    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=microseconds)


@dataclass(frozen=True)
class SpanMetadata:
    """Lightweight span metadata for DuckDB indexing."""

    span_id: str
    trace_id: str
    parent_span_id: str | None
    service_name: str
    name: str
    start_time: datetime
    end_time: datetime
    duration_ns: int
    status_code: int
    span_kind: int
    is_root: bool
    junjo_span_type: str | None  # workflow, subflow, node, run_concurrent, or None


@dataclass
class ParquetFileData:
    """Data extracted from a Parquet file for indexing."""

    file_path: str
    service_name: str
    min_time: datetime
    max_time: datetime
    row_count: int
    size_bytes: int
    spans: list[SpanMetadata]


# Columns we need for metadata indexing
# Note: We include 'attributes' to extract junjo_span_type
# Full attributes stay in Parquet for query-time access
METADATA_COLUMNS = [
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
    "attributes",  # Need to extract junjo.span_type
]


def read_parquet_metadata(file_path: str, size_bytes: int) -> ParquetFileData:
    """Read span metadata from a Parquet file.

    Only reads columns needed for DuckDB indexing. Full span data
    (attributes, events) stays in Parquet for query-time access.

    Args:
        file_path: Path to the Parquet file
        size_bytes: File size in bytes (from file_scanner)

    Returns:
        ParquetFileData with extracted metadata

    Raises:
        Exception: If file cannot be read or is malformed
    """
    # Read only metadata columns (much faster than reading full file)
    table = pq.read_table(file_path, columns=METADATA_COLUMNS)

    if table.num_rows == 0:
        raise ValueError(f"Empty Parquet file: {file_path}")

    # Convert to Python objects
    spans: list[SpanMetadata] = []
    min_time: datetime | None = None
    max_time: datetime | None = None
    service_name: str | None = None

    # Access columns by name - use to_pylist() for simple types
    span_ids = table.column("span_id").to_pylist()
    trace_ids = table.column("trace_id").to_pylist()
    parent_span_ids = table.column("parent_span_id").to_pylist()
    service_names = table.column("service_name").to_pylist()
    names = table.column("name").to_pylist()
    duration_ns_list = table.column("duration_ns").to_pylist()
    status_codes = table.column("status_code").to_pylist()
    span_kinds = table.column("span_kind").to_pylist()
    attributes_list = table.column("attributes").to_pylist()

    # For timestamps, we need to handle nanosecond precision manually
    # (pyarrow can't convert ns timestamps to Python datetime directly)
    start_time_col = table.column("start_time")
    end_time_col = table.column("end_time")

    for i in range(table.num_rows):
        # Convert nanosecond timestamps to datetime
        start_time = _timestamp_to_datetime(start_time_col[i])
        end_time = _timestamp_to_datetime(end_time_col[i])
        svc_name = service_names[i]
        parent_id = parent_span_ids[i]

        # Track time bounds
        if min_time is None or start_time < min_time:
            min_time = start_time
        if max_time is None or end_time > max_time:
            max_time = end_time

        # Track service name (assume single service per file from Go flusher)
        if service_name is None:
            service_name = svc_name

        # Determine if root span (no parent)
        is_root = parent_id is None or parent_id == ""

        # Extract junjo_span_type from attributes JSON
        junjo_span_type: str | None = None
        attrs_str = attributes_list[i]
        if attrs_str:
            try:
                attrs = json.loads(attrs_str) if isinstance(attrs_str, str) else attrs_str
                junjo_span_type = attrs.get("junjo.span_type")
            except (json.JSONDecodeError, TypeError):
                pass

        spans.append(
            SpanMetadata(
                span_id=span_ids[i],
                trace_id=trace_ids[i],
                parent_span_id=parent_id if parent_id else None,
                service_name=svc_name,
                name=names[i],
                start_time=start_time,
                end_time=end_time,
                duration_ns=duration_ns_list[i],
                status_code=status_codes[i],
                span_kind=span_kinds[i],
                is_root=is_root,
                junjo_span_type=junjo_span_type,
            )
        )

    if min_time is None or max_time is None or service_name is None:
        raise ValueError(f"Failed to extract metadata from Parquet file: {file_path}")

    logger.debug(
        f"Read {len(spans)} spans from {file_path}, "
        f"service={service_name}, time_range=[{min_time}, {max_time}]"
    )

    return ParquetFileData(
        file_path=file_path,
        service_name=service_name,
        min_time=min_time,
        max_time=max_time,
        row_count=len(spans),
        size_bytes=size_bytes,
        spans=spans,
    )
