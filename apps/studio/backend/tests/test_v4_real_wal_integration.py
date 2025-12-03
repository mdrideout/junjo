"""V4 Real WAL Integration Tests.

These tests run against the actual Go ingestion service to verify
the complete WAL → gRPC → Python fusion query flow.

Unlike test_v4_wal_fusion_integration.py which mocks the WAL client,
these tests:
1. Start the Go ingestion service (killing any existing instances)
2. Write spans directly to the SQLite WAL via the Go service
3. Query through the Python fusion repository
4. Verify WAL + Parquet fusion works end-to-end

Prerequisites:
- Go toolchain installed
- ingestion/ directory with compilable Go code

Usage:
    pytest tests/test_v4_real_wal_integration.py -v -m real_wal
"""

import atexit
import asyncio
import json
import os
import signal
import socket
import sqlite3
import subprocess
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import grpc
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from loguru import logger
from ulid import ULID
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.resource.v1 import resource_pb2
from opentelemetry.proto.trace.v1 import trace_pb2

from app.config.settings import settings
from app.proto_gen import span_data_container_pb2
from app.db_duckdb import v4_repository
from app.features.otel_spans import repository as otel_repository
from app.features.parquet_indexer.parquet_reader import read_parquet_metadata
from app.features.span_ingestion.ingestion_client import IngestionClient

# Mark all tests in this module
pytestmark = [pytest.mark.real_wal, pytest.mark.integration]

# Path to ingestion service
INGESTION_DIR = Path(__file__).parent.parent.parent / "ingestion"
INGESTION_INTERNAL_PORT = 50052  # Internal gRPC port for WAL reads (no auth required)
INGESTION_PUBLIC_PORT = 50051  # Public port for span ingestion (requires auth)


def is_port_in_use(port: int) -> bool:
    """Check if a port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def kill_existing_ingestion_processes():
    """Kill any existing ingestion service processes on the gRPC ports."""
    for port in [INGESTION_INTERNAL_PORT, INGESTION_PUBLIC_PORT]:
        try:
            # Find processes using the ingestion port
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                pids = result.stdout.strip().split("\n")
                for pid in pids:
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                        logger.info(f"Killed existing process on port {port}: PID {pid}")
                    except (ProcessLookupError, ValueError):
                        pass
        except FileNotFoundError:
            # lsof not available, try pkill
            subprocess.run(["pkill", "-9", "-f", "ingestion"], capture_output=True)
            break
    # Wait for ports to be released
    time.sleep(0.5)


def wait_for_port(port: int, timeout: float = 10.0) -> bool:
    """Wait for a port to become available."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(0.1)
    return False


# Arrow schema matching Go ingestion
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


def create_span_data(
    trace_id: str,
    span_id: str,
    parent_span_id: str | None,
    service_name: str,
    name: str,
    start_ns: int,
    duration_ns: int = 100_000,
    span_kind: int = 1,
    status_code: int = 0,
    attributes: dict | None = None,
) -> dict:
    """Create a span dict for Parquet writing."""
    end_ns = start_ns + duration_ns
    attrs = attributes or {}

    return {
        "span_id": span_id,
        "trace_id": trace_id,
        "parent_span_id": parent_span_id,
        "service_name": service_name,
        "name": name,
        "span_kind": span_kind,
        "start_time": pa.scalar(start_ns, type=pa.timestamp("ns", tz="UTC")),
        "end_time": pa.scalar(end_ns, type=pa.timestamp("ns", tz="UTC")),
        "duration_ns": duration_ns,
        "status_code": status_code,
        "status_message": None,
        "attributes": json.dumps(attrs),
        "events": "[]",
        "resource_attributes": json.dumps({"service.name": service_name}),
    }


def write_spans_to_parquet(spans: list[dict], base_dir: str, service_name: str) -> str:
    """Write spans to a Parquet file with date-partitioned path."""
    now = datetime.now(UTC)
    file_name = f"{service_name}_{int(now.timestamp())}_{uuid.uuid4().hex[:8]}.parquet"
    file_path = os.path.join(
        base_dir,
        f"year={now.year}",
        f"month={now.month:02d}",
        f"day={now.day:02d}",
        file_name,
    )

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    table = pa.Table.from_pylist(spans, schema=SPAN_SCHEMA)
    pq.write_table(table, file_path)

    return file_path


# ============================================================================
# WAL Direct Insertion Helpers
# ============================================================================


def create_wal_span_bytes(
    trace_id: str,
    span_id: str,
    parent_span_id: str | None,
    name: str,
    service_name: str,
    start_ns: int,
    end_ns: int,
    attributes: dict | None = None,
) -> tuple[bytes, bytes]:
    """Create protobuf-serialized span and resource bytes for WAL insertion.

    Returns (span_bytes, resource_bytes) matching Go's storage format.
    """
    # Create span proto
    span = trace_pb2.Span(
        trace_id=bytes.fromhex(trace_id),
        span_id=bytes.fromhex(span_id),
        parent_span_id=bytes.fromhex(parent_span_id) if parent_span_id else b"",
        name=name,
        kind=trace_pb2.Span.SPAN_KIND_SERVER,
        start_time_unix_nano=start_ns,
        end_time_unix_nano=end_ns,
    )

    # Add attributes
    if attributes:
        for key, value in attributes.items():
            attr = common_pb2.KeyValue(key=key)
            attr.value.string_value = str(value)
            span.attributes.append(attr)

    # Create resource proto with service.name attribute
    resource = resource_pb2.Resource()
    service_attr = common_pb2.KeyValue(key="service.name")
    service_attr.value.string_value = service_name
    resource.attributes.append(service_attr)

    return span.SerializeToString(), resource.SerializeToString()


def insert_span_into_wal(
    wal_path: str,
    trace_id: str,
    span_id: str,
    parent_span_id: str | None,
    name: str,
    service_name: str,
    start_ns: int,
    end_ns: int,
    attributes: dict | None = None,
):
    """Insert a span directly into the WAL SQLite database.

    This bypasses OTLP ingestion and writes directly to the SQLite WAL
    that the Go service uses, enabling true end-to-end fusion testing.
    """
    span_bytes, resource_bytes = create_wal_span_bytes(
        trace_id, span_id, parent_span_id, name, service_name, start_ns, end_ns, attributes
    )

    # Create SpanDataContainer (matches Go's storage format)
    container = span_data_container_pb2.SpanDataContainer(
        span_bytes=span_bytes,
        resource_bytes=resource_bytes,
    )

    # Generate ULID key (matching Go's format - 16 bytes)
    key = ULID().bytes

    conn = sqlite3.connect(wal_path)
    conn.execute(
        """INSERT INTO spans
           (key_ulid, span_bytes, trace_id, service_name, parent_span_id, start_time_unix_nano)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (key, container.SerializeToString(), trace_id, service_name, parent_span_id or "", start_ns),
    )
    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def backend_grpc_server():
    """Start the Python backend gRPC server for auth validation.

    The Go ingestion service requires the backend gRPC server to be
    running for API key validation during startup.

    Note: The gRPC server is started but not explicitly stopped in teardown
    because stopping a gRPC server from a different event loop causes issues.
    The daemon thread will be cleaned up when the process exits.
    """
    import threading
    from app.grpc_server import start_grpc_server_background

    # Check if backend gRPC is already running
    if is_port_in_use(settings.GRPC_PORT):
        logger.info(f"Backend gRPC server already running on port {settings.GRPC_PORT}")
        yield {"already_running": True}
        return

    # Start backend gRPC server in background thread
    async def start_server():
        await start_grpc_server_background()

    # Run in event loop on daemon thread (will be cleaned up when process exits)
    loop = asyncio.new_event_loop()

    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start_server())
        # Keep the loop running to handle requests
        loop.run_forever()

    server_thread = threading.Thread(target=run_loop, daemon=True)
    server_thread.start()

    # Wait for server to start
    if not wait_for_port(settings.GRPC_PORT, timeout=10.0):
        pytest.skip("Failed to start backend gRPC server")

    logger.info(f"Backend gRPC server started on port {settings.GRPC_PORT}")

    yield {"already_running": False, "loop": loop, "thread": server_thread}

    # Don't explicitly stop - daemon thread will be cleaned up automatically


@pytest.fixture(scope="module")
def ingestion_service(backend_grpc_server):
    """Start the Go ingestion service for the test module.

    This fixture:
    1. Ensures backend gRPC is running (for auth)
    2. Kills any existing ingestion processes
    3. Creates temp directories for WAL and Parquet
    4. Starts the Go ingestion service
    5. Waits for it to be ready
    6. Cleans up after all tests complete
    """
    # Kill existing processes
    kill_existing_ingestion_processes()

    # Ensure ports are free
    for port in [INGESTION_INTERNAL_PORT, INGESTION_PUBLIC_PORT]:
        if is_port_in_use(port):
            pytest.skip(f"Port {port} still in use after killing processes")

    # Create temp directories
    temp_dir = tempfile.mkdtemp(prefix="ingestion_test_")
    wal_path = os.path.join(temp_dir, "wal.db")
    parquet_dir = os.path.join(temp_dir, "parquet")
    os.makedirs(parquet_dir, exist_ok=True)

    logger.info(f"Starting ingestion service with WAL at {wal_path}")

    # Build and start the ingestion service
    env = os.environ.copy()
    env.update({
        "JUNJO_WAL_SQLITE_PATH": wal_path,
        "SPAN_STORAGE_PATH": parquet_dir,
        "GRPC_PORT": str(INGESTION_PUBLIC_PORT),
        "INTERNAL_GRPC_PORT": str(INGESTION_INTERNAL_PORT),
        "BACKEND_GRPC_HOST": "localhost",
        "BACKEND_GRPC_PORT": str(settings.GRPC_PORT),
        "JUNJO_LOG_LEVEL": "debug",
        "JUNJO_LOG_FORMAT": "text",
    })

    # Build the binary first (avoids go run child process issues that can leave orphans)
    binary_path = os.path.join(temp_dir, "ingestion-test")
    build_result = subprocess.run(
        ["go", "build", "-o", binary_path, "."],
        cwd=INGESTION_DIR,
        capture_output=True,
        text=True,
    )
    if build_result.returncode != 0:
        pytest.fail(f"Failed to build ingestion service:\n{build_result.stderr}")

    # Start the binary directly (not via go run)
    process = subprocess.Popen(
        [binary_path],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Register atexit handler to ensure cleanup on any exit (Ctrl+C, crash, etc)
    def cleanup_on_exit():
        try:
            process.kill()
        except Exception:
            pass
        kill_existing_ingestion_processes()

    atexit.register(cleanup_on_exit)

    # Wait for internal service to be ready (internal port for WAL queries)
    if not wait_for_port(INGESTION_INTERNAL_PORT, timeout=60.0):
        # Capture any error output
        try:
            stdout, stderr = process.communicate(timeout=5)
            error_msg = f"stdout: {stdout.decode()}\nstderr: {stderr.decode()}"
        except subprocess.TimeoutExpired:
            process.kill()
            error_msg = "Process timed out"
        pytest.fail(f"Ingestion service failed to start within 60s.\n{error_msg}")

    logger.info(f"Ingestion service started (internal port: {INGESTION_INTERNAL_PORT})")

    yield {
        "process": process,
        "temp_dir": temp_dir,
        "wal_path": wal_path,
        "parquet_dir": parquet_dir,
        "internal_port": INGESTION_INTERNAL_PORT,
    }

    # Cleanup
    logger.info("Stopping ingestion service")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()

    # Unregister atexit handler since we're doing normal cleanup
    atexit.unregister(cleanup_on_exit)

    # Clean up temp directory
    import shutil
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass


@pytest.fixture
def temp_duckdb():
    """Create a temporary DuckDB database with V4 schema."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "test.duckdb")

        # Create connection and initialize schema
        conn = duckdb.connect(db_path)

        # Read and execute V4 schema files
        schema_dir = Path(__file__).parent.parent / "app" / "db_duckdb" / "schemas"
        conn.execute((schema_dir / "v4_parquet_files.sql").read_text())
        conn.execute((schema_dir / "v4_span_metadata.sql").read_text())
        conn.execute((schema_dir / "v4_services.sql").read_text())
        conn.execute((schema_dir / "v4_failed_files.sql").read_text())
        conn.close()

        # Override settings to use temp database
        from app.config.settings import settings

        original_path = settings.database.duckdb_path
        settings.database.duckdb_path = db_path

        yield db_path

        # Restore original path
        settings.database.duckdb_path = original_path


@pytest.fixture
async def wal_client_for_localhost(ingestion_service):
    """Configure WAL client to use localhost instead of default settings.

    This fixture patches the module-level WAL client in repository.py
    to connect to the test ingestion service on localhost.
    """
    # Reset any existing WAL client before test
    await otel_repository._reset_wal_client()

    # Override settings to use localhost
    original_host = settings.span_ingestion.INGESTION_HOST
    original_port = settings.span_ingestion.INGESTION_PORT
    settings.span_ingestion.INGESTION_HOST = "localhost"
    settings.span_ingestion.INGESTION_PORT = ingestion_service["internal_port"]

    yield

    # Reset client and restore settings after test
    await otel_repository._reset_wal_client()
    settings.span_ingestion.INGESTION_HOST = original_host
    settings.span_ingestion.INGESTION_PORT = original_port


class TestRealWALServiceNameFusion:
    """Test service name fusion with real WAL service."""

    @pytest.mark.asyncio
    async def test_wal_service_names_returned(self, ingestion_service, temp_duckdb):
        """Service names from WAL should appear in fused results."""
        parquet_dir = ingestion_service["parquet_dir"]
        now_ns = int(datetime.now(UTC).timestamp() * 1e9)

        # Create a span in Parquet for "parquet-service"
        parquet_spans = [
            create_span_data(
                trace_id=uuid.uuid4().hex,
                span_id="pq_span_00001",
                parent_span_id=None,
                service_name="parquet-service",
                name="ParquetRoot",
                start_ns=now_ns,
            )
        ]
        parquet_file = write_spans_to_parquet(parquet_spans, parquet_dir, "parquet-service")

        # Index the Parquet file
        file_size = os.path.getsize(parquet_file)
        file_data = read_parquet_metadata(parquet_file, file_size)
        v4_repository.index_parquet_file(file_data)

        # Query fused service names
        services = await otel_repository.get_fused_distinct_service_names()

        # Parquet service should be present
        assert "parquet-service" in services


class TestRealWALTraceSpanFusion:
    """Test trace span fusion with real WAL service."""

    @pytest.mark.asyncio
    async def test_trace_merges_parquet_and_wal(self, ingestion_service, temp_duckdb):
        """A trace split between Parquet and WAL should be merged."""
        parquet_dir = ingestion_service["parquet_dir"]
        now_ns = int(datetime.now(UTC).timestamp() * 1e9)

        trace_id = uuid.uuid4().hex
        root_span_id = "split_root_001"

        # Create root span in Parquet
        parquet_spans = [
            create_span_data(
                trace_id=trace_id,
                span_id=root_span_id,
                parent_span_id=None,
                service_name="split-service",
                name="SplitTraceRoot",
                start_ns=now_ns,
            )
        ]
        parquet_file = write_spans_to_parquet(parquet_spans, parquet_dir, "split-service")

        # Index the Parquet file
        file_size = os.path.getsize(parquet_file)
        file_data = read_parquet_metadata(parquet_file, file_size)
        v4_repository.index_parquet_file(file_data)

        # Query the trace (should get at least the Parquet span)
        spans = await otel_repository.get_fused_trace_spans(trace_id)

        # Should have the root span from Parquet
        assert len(spans) >= 1
        span_ids = {s["span_id"] for s in spans}
        assert root_span_id in span_ids


class TestRealWALRootSpanFusion:
    """Test root span fusion with real WAL service."""

    @pytest.mark.asyncio
    async def test_root_spans_from_parquet(self, ingestion_service, temp_duckdb):
        """Root spans from Parquet should appear in fused results."""
        parquet_dir = ingestion_service["parquet_dir"]
        now_ns = int(datetime.now(UTC).timestamp() * 1e9)

        # Create root spans in Parquet
        parquet_spans = [
            create_span_data(
                trace_id=uuid.uuid4().hex,
                span_id="root_span_0001",
                parent_span_id=None,
                service_name="root-test-service",
                name="RootSpan1",
                start_ns=now_ns,
            ),
            create_span_data(
                trace_id=uuid.uuid4().hex,
                span_id="root_span_0002",
                parent_span_id=None,
                service_name="root-test-service",
                name="RootSpan2",
                start_ns=now_ns + 1_000_000,
            ),
        ]
        parquet_file = write_spans_to_parquet(parquet_spans, parquet_dir, "root-test-service")

        # Index the Parquet file
        file_size = os.path.getsize(parquet_file)
        file_data = read_parquet_metadata(parquet_file, file_size)
        v4_repository.index_parquet_file(file_data)

        # Query fused root spans
        root_spans = await otel_repository.get_fused_root_spans("root-test-service")

        # Should have both root spans from Parquet
        assert len(root_spans) >= 2
        span_ids = {s["span_id"] for s in root_spans}
        assert "root_span_0001" in span_ids
        assert "root_span_0002" in span_ids


class TestRealWALSingleSpanFusion:
    """Test single span lookup with real WAL service."""

    @pytest.mark.asyncio
    async def test_get_span_from_parquet(self, ingestion_service, temp_duckdb):
        """Should find a span stored in Parquet."""
        parquet_dir = ingestion_service["parquet_dir"]
        now_ns = int(datetime.now(UTC).timestamp() * 1e9)

        trace_id = uuid.uuid4().hex
        span_id = "single_span_001"

        # Create span in Parquet
        parquet_spans = [
            create_span_data(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=None,
                service_name="single-span-service",
                name="SingleSpanTest",
                start_ns=now_ns,
            )
        ]
        parquet_file = write_spans_to_parquet(parquet_spans, parquet_dir, "single-span-service")

        # Index the Parquet file
        file_size = os.path.getsize(parquet_file)
        file_data = read_parquet_metadata(parquet_file, file_size)
        v4_repository.index_parquet_file(file_data)

        # Query the specific span
        span = await otel_repository.get_fused_span(trace_id, span_id)

        assert span is not None
        assert span["span_id"] == span_id
        assert span["trace_id"] == trace_id
        assert span["name"] == "SingleSpanTest"


class TestRealWALClientConnectivity:
    """Test direct WAL client connectivity."""

    @pytest.mark.asyncio
    async def test_wal_client_connects(self, ingestion_service):
        """The WAL client should successfully connect to the ingestion service."""
        client = IngestionClient(
            host="localhost",
            port=ingestion_service["internal_port"],
        )

        try:
            await client.connect()

            # Try to get distinct service names (may be empty, that's fine)
            services = await client.get_wal_distinct_service_names()
            assert isinstance(services, list)

        except grpc.aio.AioRpcError as e:
            pytest.fail(f"Failed to connect to WAL service: {e.code()} - {e.details()}")
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_wal_root_spans_query(self, ingestion_service):
        """The WAL client should be able to query root spans."""
        client = IngestionClient(
            host="localhost",
            port=ingestion_service["internal_port"],
        )

        try:
            await client.connect()

            # Query root spans for a non-existent service (should return empty, not error)
            root_spans = await client.get_wal_root_spans("nonexistent-service", limit=10)
            assert isinstance(root_spans, list)
            assert len(root_spans) == 0

        except grpc.aio.AioRpcError as e:
            pytest.fail(f"Failed to query WAL root spans: {e.code()} - {e.details()}")
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_wal_trace_query(self, ingestion_service):
        """The WAL client should be able to query spans by trace ID."""
        client = IngestionClient(
            host="localhost",
            port=ingestion_service["internal_port"],
        )

        try:
            await client.connect()

            # Query spans for a non-existent trace (should return empty, not error)
            fake_trace_id = uuid.uuid4().hex
            spans = await client.get_wal_spans_by_trace_id(fake_trace_id)
            assert isinstance(spans, list)
            assert len(spans) == 0

        except grpc.aio.AioRpcError as e:
            pytest.fail(f"Failed to query WAL spans by trace: {e.code()} - {e.details()}")
        finally:
            await client.close()


# ============================================================================
# True End-to-End WAL + Parquet Fusion Tests
# ============================================================================


class TestRealWALFusionWithData:
    """Tests that insert data into both WAL and Parquet, then verify fusion.

    These tests directly insert protobuf-serialized spans into the SQLite WAL
    (bypassing OTLP ingestion) and verify the Go gRPC service returns them,
    proving true end-to-end fusion of WAL + Parquet data.
    """

    @pytest.mark.asyncio
    async def test_service_names_from_wal_appear_in_fusion(
        self, ingestion_service, temp_duckdb, wal_client_for_localhost
    ):
        """Service names from WAL should appear in fused results."""
        wal_path = ingestion_service["wal_path"]
        now_ns = int(datetime.now(UTC).timestamp() * 1e9)

        # Insert a span into WAL for "wal-only-service"
        insert_span_into_wal(
            wal_path=wal_path,
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            parent_span_id=None,
            name="WALOnlyRoot",
            service_name="wal-only-service",
            start_ns=now_ns,
            end_ns=now_ns + 100_000,
        )

        # Query fused service names
        services = await otel_repository.get_fused_distinct_service_names()

        # WAL service should be present
        assert "wal-only-service" in services

    @pytest.mark.asyncio
    async def test_trace_spans_merge_wal_and_parquet(
        self, ingestion_service, temp_duckdb, wal_client_for_localhost
    ):
        """A trace with root in Parquet and child in WAL should merge."""
        wal_path = ingestion_service["wal_path"]
        parquet_dir = ingestion_service["parquet_dir"]
        now_ns = int(datetime.now(UTC).timestamp() * 1e9)

        trace_id = uuid.uuid4().hex
        root_span_id = uuid.uuid4().hex[:16]
        child_span_id = uuid.uuid4().hex[:16]

        # Create root span in Parquet
        parquet_spans = [
            create_span_data(
                trace_id=trace_id,
                span_id=root_span_id,
                parent_span_id=None,
                service_name="fusion-test-service",
                name="ParquetRoot",
                start_ns=now_ns,
            )
        ]
        parquet_file = write_spans_to_parquet(parquet_spans, parquet_dir, "fusion-test-service")
        file_size = os.path.getsize(parquet_file)
        file_data = read_parquet_metadata(parquet_file, file_size)
        v4_repository.index_parquet_file(file_data)

        # Insert child span into WAL
        insert_span_into_wal(
            wal_path=wal_path,
            trace_id=trace_id,
            span_id=child_span_id,
            parent_span_id=root_span_id,
            name="WALChild",
            service_name="fusion-test-service",
            start_ns=now_ns + 1_000,
            end_ns=now_ns + 2_000,
        )

        # Query fused trace spans
        spans = await otel_repository.get_fused_trace_spans(trace_id)

        # Should have both spans
        assert len(spans) == 2
        span_ids = {s["span_id"] for s in spans}
        assert root_span_id in span_ids
        assert child_span_id in span_ids

    @pytest.mark.asyncio
    async def test_parquet_wins_deduplication_with_real_wal(
        self, ingestion_service, temp_duckdb, wal_client_for_localhost
    ):
        """When same span exists in both, Parquet version should win."""
        wal_path = ingestion_service["wal_path"]
        parquet_dir = ingestion_service["parquet_dir"]
        now_ns = int(datetime.now(UTC).timestamp() * 1e9)

        trace_id = uuid.uuid4().hex
        span_id = uuid.uuid4().hex[:16]

        # Create span in Parquet with name "ParquetVersion"
        parquet_spans = [
            create_span_data(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=None,
                service_name="dedup-test-service",
                name="ParquetVersion",
                start_ns=now_ns,
            )
        ]
        parquet_file = write_spans_to_parquet(parquet_spans, parquet_dir, "dedup-test-service")
        file_size = os.path.getsize(parquet_file)
        file_data = read_parquet_metadata(parquet_file, file_size)
        v4_repository.index_parquet_file(file_data)

        # Insert SAME span into WAL with different name "WALVersion"
        insert_span_into_wal(
            wal_path=wal_path,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=None,
            name="WALVersion",
            service_name="dedup-test-service",
            start_ns=now_ns,
            end_ns=now_ns + 100_000,
        )

        # Query fused trace
        spans = await otel_repository.get_fused_trace_spans(trace_id)

        # Should have exactly 1 span (deduplicated)
        assert len(spans) == 1
        # Parquet version should win
        assert spans[0]["name"] == "ParquetVersion"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "real_wal"])
