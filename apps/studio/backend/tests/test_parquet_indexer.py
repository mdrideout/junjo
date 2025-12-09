"""Tests for V4 Parquet indexer.

Tests the complete flow: file scanning → Parquet reading → DuckDB indexing.
Uses pyarrow to create real Parquet files matching the Go ingestion schema.
"""

import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.db_duckdb import v4_repository
from app.features.parquet_indexer.file_scanner import ParquetFileInfo, scan_parquet_files
from app.features.parquet_indexer.parquet_reader import read_parquet_metadata

# ============================================================================
# Test Fixtures
# ============================================================================


# Arrow schema matching Go ingestion (parquet_writer.go)
SPAN_SCHEMA = pa.schema(
    [
        pa.field("span_id", pa.string(), nullable=False),
        pa.field("trace_id", pa.string(), nullable=False),
        pa.field("parent_span_id", pa.string(), nullable=True),
        pa.field("service_name", pa.string(), nullable=False),
        pa.field("name", pa.string(), nullable=False),
        pa.field("span_kind", pa.int8(), nullable=False),
        pa.field("start_time", pa.timestamp("ns", tz="UTC"), nullable=False),
        pa.field("end_time", pa.timestamp("ns", tz="UTC"), nullable=False),
        pa.field("duration_ns", pa.int64(), nullable=False),
        pa.field("status_code", pa.int8(), nullable=False),
        pa.field("status_message", pa.string(), nullable=True),
        pa.field("attributes", pa.string(), nullable=False),
        pa.field("events", pa.string(), nullable=False),
        pa.field("resource_attributes", pa.string(), nullable=False),
    ]
)


def create_test_parquet_file(
    base_dir: str,
    service_name: str = "test-service",
    span_count: int = 3,
    include_root_span: bool = True,
) -> str:
    """Create a test Parquet file matching Go ingestion schema.

    Args:
        base_dir: Directory to create file in
        service_name: Service name for spans
        span_count: Number of spans to create
        include_root_span: If True, first span has no parent (is root)

    Returns:
        Absolute path to created Parquet file
    """
    trace_id = uuid.uuid4().hex
    now = datetime.now(UTC)

    # Build span data
    spans = []
    for i in range(span_count):
        span_id = uuid.uuid4().hex[:16]
        parent_id = None if (i == 0 and include_root_span) else uuid.uuid4().hex[:16]
        start_ns = int(now.timestamp() * 1e9) + i * 1000000
        duration_ns = 100000 + i * 10000
        end_ns = start_ns + duration_ns

        spans.append(
            {
                "span_id": span_id,
                "trace_id": trace_id,
                "parent_span_id": parent_id,
                "service_name": service_name,
                "name": f"span-{i}",
                "span_kind": 1,  # SPAN_KIND_SERVER
                "start_time": pa.scalar(start_ns, type=pa.timestamp("ns", tz="UTC")),
                "end_time": pa.scalar(end_ns, type=pa.timestamp("ns", tz="UTC")),
                "duration_ns": duration_ns,
                "status_code": 0,  # STATUS_CODE_UNSET
                "status_message": None,
                "attributes": "{}",
                "events": "[]",
                "resource_attributes": '{"service.name": "' + service_name + '"}',
            }
        )

    # Convert to Arrow table
    table = pa.Table.from_pylist(spans, schema=SPAN_SCHEMA)

    # Create date-partitioned path like Go flusher
    file_name = f"{service_name}_{int(now.timestamp())}_{uuid.uuid4().hex[:8]}.parquet"
    file_path = os.path.join(
        base_dir,
        f"year={now.year}",
        f"month={now.month:02d}",
        f"day={now.day:02d}",
        file_name,
    )

    # Ensure directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # Write Parquet file
    pq.write_table(table, file_path)

    return file_path


@pytest.fixture
def temp_parquet_dir():
    """Create a temporary directory for Parquet files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def temp_duckdb():
    """Create a temporary DuckDB database with V4 schema.

    Overrides the global settings to use the temp database.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "test.duckdb")

        # Create connection and initialize schema
        conn = duckdb.connect(db_path)

        # Read and execute V4 schema files
        schema_dir = Path(__file__).parent.parent / "app" / "db_duckdb" / "schemas"
        conn.execute((schema_dir / "v4_parquet_files.sql").read_text())
        conn.execute((schema_dir / "v4_span_metadata.sql").read_text())
        conn.execute((schema_dir / "v4_file_services.sql").read_text())
        conn.execute((schema_dir / "v4_failed_files.sql").read_text())
        conn.close()

        # Override settings to use temp database
        from app.config.settings import settings

        original_path = settings.database.duckdb_path
        settings.database.duckdb_path = db_path

        yield db_path

        # Restore original path
        settings.database.duckdb_path = original_path


# ============================================================================
# File Scanner Tests
# ============================================================================


@pytest.mark.unit
def test_scan_empty_directory(temp_parquet_dir):
    """scan_parquet_files returns empty list when no .parquet files exist."""
    result = scan_parquet_files(temp_parquet_dir)
    assert result == []


@pytest.mark.unit
def test_scan_nonexistent_path():
    """scan_parquet_files handles missing directory gracefully."""
    result = scan_parquet_files("/nonexistent/path/that/does/not/exist")
    assert result == []


@pytest.mark.unit
def test_scan_finds_parquet_files(temp_parquet_dir):
    """scan_parquet_files finds files in nested date-partitioned structure."""
    # Create test files
    path1 = create_test_parquet_file(temp_parquet_dir, "service-a")
    path2 = create_test_parquet_file(temp_parquet_dir, "service-b")

    result = scan_parquet_files(temp_parquet_dir)

    assert len(result) == 2
    paths = {f.path for f in result}
    assert path1 in paths
    assert path2 in paths

    # Verify ParquetFileInfo fields
    for file_info in result:
        assert isinstance(file_info, ParquetFileInfo)
        assert file_info.size_bytes > 0
        assert file_info.mtime > 0


# ============================================================================
# Parquet Reader Tests
# ============================================================================


@pytest.mark.unit
def test_read_parquet_metadata(temp_parquet_dir):
    """read_parquet_metadata extracts correct span metadata from valid file."""
    file_path = create_test_parquet_file(temp_parquet_dir, "my-service", span_count=5)
    file_size = os.path.getsize(file_path)

    result = read_parquet_metadata(file_path, file_size)

    assert result.file_path == file_path
    assert result.service_name == "my-service"
    assert result.row_count == 5
    assert result.size_bytes == file_size
    assert len(result.spans) == 5

    # Verify span metadata fields
    for span in result.spans:
        assert span.service_name == "my-service"
        assert span.span_id
        assert span.trace_id
        assert span.start_time
        assert span.end_time
        assert span.duration_ns > 0


@pytest.mark.unit
def test_read_parquet_with_root_spans(temp_parquet_dir):
    """read_parquet_metadata correctly identifies root spans (no parent)."""
    file_path = create_test_parquet_file(
        temp_parquet_dir, "root-test", span_count=3, include_root_span=True
    )
    file_size = os.path.getsize(file_path)

    result = read_parquet_metadata(file_path, file_size)

    # First span should be root (no parent)
    root_spans = [s for s in result.spans if s.is_root]
    assert len(root_spans) == 1

    # Other spans should have parents
    non_root_spans = [s for s in result.spans if not s.is_root]
    assert len(non_root_spans) == 2


@pytest.mark.unit
def test_read_parquet_time_bounds(temp_parquet_dir):
    """read_parquet_metadata extracts min/max time correctly."""
    file_path = create_test_parquet_file(temp_parquet_dir, "time-test", span_count=5)
    file_size = os.path.getsize(file_path)

    result = read_parquet_metadata(file_path, file_size)

    # min_time should be earliest start_time
    # max_time should be latest end_time
    span_start_times = [s.start_time for s in result.spans]
    span_end_times = [s.end_time for s in result.spans]

    assert result.min_time == min(span_start_times)
    assert result.max_time == max(span_end_times)


# ============================================================================
# V4 Repository Tests
# ============================================================================


@pytest.mark.unit
def test_index_parquet_file(temp_parquet_dir, temp_duckdb):
    """index_parquet_file inserts into all 3 tables in a transaction."""
    file_path = create_test_parquet_file(temp_parquet_dir, "index-test", span_count=3)
    file_size = os.path.getsize(file_path)
    file_data = read_parquet_metadata(file_path, file_size)

    # Index the file
    span_count = v4_repository.index_parquet_file(file_data)
    assert span_count == 3

    # Verify parquet_files table
    conn = duckdb.connect(temp_duckdb)
    files = conn.execute("SELECT * FROM parquet_files").fetchall()
    assert len(files) == 1
    assert files[0][1] == file_path  # file_path column

    # Verify span_metadata table
    spans = conn.execute("SELECT * FROM span_metadata").fetchall()
    assert len(spans) == 3

    # Verify file_services table
    file_services = conn.execute("SELECT * FROM file_services").fetchall()
    assert len(file_services) == 1
    assert file_services[0][1] == "index-test"  # service_name
    assert file_services[0][2] == 3  # span_count

    conn.close()


@pytest.mark.unit
def test_get_indexed_file_paths(temp_parquet_dir, temp_duckdb):
    """get_indexed_file_paths returns set of already-indexed paths."""
    # Initially empty
    paths = v4_repository.get_indexed_file_paths()
    assert paths == set()

    # Index a file
    file_path = create_test_parquet_file(temp_parquet_dir, "paths-test")
    file_size = os.path.getsize(file_path)
    file_data = read_parquet_metadata(file_path, file_size)
    v4_repository.index_parquet_file(file_data)

    # Now should contain the path
    paths = v4_repository.get_indexed_file_paths()
    assert file_path in paths


@pytest.mark.unit
def test_deduplication(temp_parquet_dir, temp_duckdb):
    """Same file cannot be indexed twice (unique constraint)."""
    file_path = create_test_parquet_file(temp_parquet_dir, "dedup-test")
    file_size = os.path.getsize(file_path)
    file_data = read_parquet_metadata(file_path, file_size)

    # First index succeeds
    v4_repository.index_parquet_file(file_data)

    # Second index fails (duplicate file_path)
    with pytest.raises(Exception):
        v4_repository.index_parquet_file(file_data)


# ============================================================================
# Failed File Tracking Tests
# ============================================================================


@pytest.mark.unit
def test_record_failed_file(temp_duckdb):
    """record_failed_file records failure in failed_parquet_files table."""
    v4_repository.record_failed_file(
        file_path="/path/to/bad.parquet",
        error_type="ArrowInvalid",
        error_message="File is corrupt",
        file_size=1234,
    )

    # Verify it's recorded
    failed = v4_repository.get_failed_files()
    assert len(failed) == 1
    assert failed[0]["file_path"] == "/path/to/bad.parquet"
    assert failed[0]["error_type"] == "ArrowInvalid"
    assert failed[0]["error_message"] == "File is corrupt"
    assert failed[0]["file_size"] == 1234
    assert failed[0]["retry_count"] == 1


@pytest.mark.unit
def test_get_failed_file_paths(temp_duckdb):
    """get_failed_file_paths returns set of paths to skip."""
    # Initially empty
    paths = v4_repository.get_failed_file_paths()
    assert paths == set()

    # Record a failure
    v4_repository.record_failed_file(
        file_path="/path/to/bad.parquet",
        error_type="ValueError",
        error_message="Empty file",
    )

    # Now should contain the path
    paths = v4_repository.get_failed_file_paths()
    assert "/path/to/bad.parquet" in paths


@pytest.mark.unit
def test_failed_file_retry_count(temp_duckdb):
    """retry_count increments on repeated failures."""
    # First failure
    v4_repository.record_failed_file(
        file_path="/path/to/bad.parquet",
        error_type="Error1",
        error_message="First error",
    )

    failed = v4_repository.get_failed_files()
    assert failed[0]["retry_count"] == 1

    # Second failure (same file)
    v4_repository.record_failed_file(
        file_path="/path/to/bad.parquet",
        error_type="Error2",
        error_message="Second error",
    )

    failed = v4_repository.get_failed_files()
    assert len(failed) == 1
    assert failed[0]["retry_count"] == 2
    assert failed[0]["error_type"] == "Error2"  # Updated to latest


@pytest.mark.unit
def test_clear_failed_file(temp_duckdb):
    """clear_failed_file removes a file from the failed list."""
    v4_repository.record_failed_file(
        file_path="/path/to/bad.parquet",
        error_type="Error",
        error_message="Test",
    )

    # Clear it
    result = v4_repository.clear_failed_file("/path/to/bad.parquet")
    assert result is True

    # Should be gone
    paths = v4_repository.get_failed_file_paths()
    assert "/path/to/bad.parquet" not in paths

    # Clearing again returns False
    result = v4_repository.clear_failed_file("/path/to/bad.parquet")
    assert result is False


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.integration
def test_full_indexing_flow(temp_parquet_dir, temp_duckdb):
    """Full flow: create Parquet → scan → read → index → verify in DuckDB."""
    # Create multiple test files
    path1 = create_test_parquet_file(temp_parquet_dir, "service-alpha", span_count=5)
    path2 = create_test_parquet_file(temp_parquet_dir, "service-beta", span_count=3)

    # Scan for files
    files = scan_parquet_files(temp_parquet_dir)
    assert len(files) == 2

    # Get indexed paths (should be empty)
    indexed = v4_repository.get_indexed_file_paths()
    assert len(indexed) == 0

    # Index each file
    for file_info in files:
        file_data = read_parquet_metadata(file_info.path, file_info.size_bytes)
        v4_repository.index_parquet_file(file_data)

    # Verify all indexed
    indexed = v4_repository.get_indexed_file_paths()
    assert path1 in indexed
    assert path2 in indexed

    # Verify DuckDB contents
    conn = duckdb.connect(temp_duckdb)

    # 2 files
    files_count = conn.execute("SELECT COUNT(*) FROM parquet_files").fetchone()[0]
    assert files_count == 2

    # 8 total spans (5 + 3)
    spans_count = conn.execute("SELECT COUNT(*) FROM span_metadata").fetchone()[0]
    assert spans_count == 8

    # 2 services in file_services (one per file)
    file_services = conn.execute(
        "SELECT service_name, span_count FROM file_services ORDER BY service_name"
    ).fetchall()
    assert len(file_services) == 2
    assert file_services[0] == ("service-alpha", 5)
    assert file_services[1] == ("service-beta", 3)

    conn.close()


@pytest.mark.integration
def test_corrupt_file_handling(temp_parquet_dir, temp_duckdb):
    """Corrupt file is recorded and doesn't block other files."""
    # Create a valid file
    valid_path = create_test_parquet_file(temp_parquet_dir, "valid-service")

    # Create a corrupt "parquet" file
    corrupt_path = os.path.join(temp_parquet_dir, "year=2025", "month=01", "day=01")
    os.makedirs(corrupt_path, exist_ok=True)
    corrupt_file = os.path.join(corrupt_path, "corrupt_file.parquet")
    with open(corrupt_file, "w") as f:
        f.write("this is not valid parquet data")

    # Scan finds both files
    files = scan_parquet_files(temp_parquet_dir)
    assert len(files) == 2

    # Process files - corrupt one should fail
    for file_info in files:
        try:
            file_data = read_parquet_metadata(file_info.path, file_info.size_bytes)
            v4_repository.index_parquet_file(file_data)
        except Exception as e:
            v4_repository.record_failed_file(
                file_info.path, type(e).__name__, str(e), file_info.size_bytes
            )

    # Valid file should be indexed
    indexed = v4_repository.get_indexed_file_paths()
    assert valid_path in indexed

    # Corrupt file should be in failed list
    failed = v4_repository.get_failed_file_paths()
    assert corrupt_file in failed

    # Failed file details available
    failed_details = v4_repository.get_failed_files()
    assert len(failed_details) == 1
    assert failed_details[0]["file_path"] == corrupt_file
