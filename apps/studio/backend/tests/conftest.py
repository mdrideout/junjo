"""Pytest fixtures for backend integration tests.

Provides shared fixtures for tests that require the Rust ingestion service.
"""

import os
import shutil
import socket
import subprocess
import tempfile
import time
from concurrent import futures
from pathlib import Path

import grpc
import pytest
from loguru import logger

from app.proto_gen import auth_pb2, auth_pb2_grpc

# Path to ingestion service
INGESTION_DIR = Path(__file__).parent.parent.parent / "ingestion"


def is_port_in_use(port: int) -> bool:
    """Check if a port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def find_free_port() -> int:
    """Reserve an available localhost TCP port for a spawned test service."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_port(port: int, timeout: float = 60.0) -> bool:
    """Wait for a port to become available."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(0.1)
    return False


def read_log_tail(path: Path, max_bytes: int = 64 * 1024) -> str:
    """Read a bounded UTF-8-safe process log tail for failure diagnostics."""
    try:
        with path.open("rb") as log_file:
            log_file.seek(0, os.SEEK_END)
            size = log_file.tell()
            log_file.seek(max(0, size - max_bytes))
            return log_file.read().decode("utf-8", errors="replace")
    except OSError as error:
        return f"Unable to read ingestion log: {error}"


@pytest.fixture(scope="module")
def mock_backend_auth_server():
    """Start a tiny in-process backend auth gRPC server for ingestion tests.

    The Rust ingestion service requires x-junjo-api-key validation on OTLP ingest.
    For backend/ingestion integration tests we don't want to bring up the full
    backend, so we run a minimal InternalAuthService that always returns is_valid=true.

    The server binds to an ephemeral port to avoid conflicting with the backend's own
    gRPC integration tests (which use port 50053).
    """

    class _AlwaysValidAuthServicer(auth_pb2_grpc.InternalAuthServiceServicer):
        def ValidateApiKey(  # noqa: N802 - protobuf naming
            self,
            request: auth_pb2.ValidateApiKeyRequest,
            context: grpc.ServicerContext,
        ) -> auth_pb2.ValidateApiKeyResponse:
            metadata = dict(context.invocation_metadata())
            if metadata.get("x-junjo-internal-token") != os.environ[
                "JUNJO_INTERNAL_GRPC_TOKEN"
            ]:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid workload token")
            return auth_pb2.ValidateApiKeyResponse(is_valid=True)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    auth_pb2_grpc.add_InternalAuthServiceServicer_to_server(_AlwaysValidAuthServicer(), server)

    port = server.add_insecure_port("127.0.0.1:0")
    if port == 0:
        pytest.fail("Failed to bind mock backend auth server to an ephemeral port")

    server.start()
    logger.info(f"Mock backend auth gRPC server started on 127.0.0.1:{port}")

    try:
        yield {"host": "127.0.0.1", "port": port}
    finally:
        server.stop(grace=0)


@pytest.fixture(scope="session")
def rust_ingestion_binary():
    """Build the Rust ingestion service once per test session.

    This fixture compiles the release binary once, which is then reused
    by rust_ingestion_service for each test module.
    """
    binary_path = INGESTION_DIR / "target" / "release" / "ingestion"

    logger.info("Building Rust ingestion service (release mode)...")
    result = subprocess.run(
        ["cargo", "build", "--release"],
        cwd=INGESTION_DIR,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        pytest.fail(f"Failed to build ingestion service:\n{result.stderr}")

    if not binary_path.exists():
        pytest.fail(f"Binary not found at {binary_path}")

    logger.info(f"Rust ingestion binary ready: {binary_path}")
    return binary_path


@pytest.fixture(scope="module")
def rust_ingestion_service(
    rust_ingestion_binary,
    mock_backend_auth_server,
    request: pytest.FixtureRequest,
):
    """Start the Rust ingestion service for integration tests.

    This fixture:
    1. Uses pre-built binary from rust_ingestion_binary (session-scoped)
    2. Allocates ephemeral public/internal ports to avoid local conflicts
    3. Creates temp directories for WAL, Parquet, and snapshot
    4. Starts the ingestion service
    5. Waits for it to be ready
    6. Cleans up after all tests in the module complete

    Usage:
        @pytest.mark.requires_ingestion_service
        async def test_something(rust_ingestion_service):
            # rust_ingestion_service contains service info
            pass
    """
    ingestion_internal_port = find_free_port()
    ingestion_public_port = find_free_port()

    # Create temp directories
    temp_dir = tempfile.mkdtemp(prefix="rust_ingestion_test_")
    wal_dir = os.path.join(temp_dir, "wal")
    parquet_dir = os.path.join(temp_dir, "parquet")
    snapshot_path = os.path.join(temp_dir, "hot_snapshot.parquet")
    log_path = Path(temp_dir) / "ingestion.log"
    os.makedirs(wal_dir, exist_ok=True)
    os.makedirs(parquet_dir, exist_ok=True)

    logger.info(f"Starting Rust ingestion service with temp dir: {temp_dir}")

    # Set environment for the service
    env = os.environ.copy()
    env.update({
        "WAL_DIR": wal_dir,
        "SNAPSHOT_PATH": snapshot_path,
        "PARQUET_OUTPUT_DIR": parquet_dir,
        "GRPC_PORT": str(ingestion_public_port),
        "INTERNAL_GRPC_PORT": str(ingestion_internal_port),
        # Integration tests need fresh snapshots on each request; cache reuse can hide
        # just-ingested spans across parametrized cases.
        "PREPARE_HOT_SNAPSHOT_CACHE_TTL_MS": "0",
        # Provide a tiny in-process backend auth gRPC so OTLP ingest can validate API keys.
        "BACKEND_GRPC_HOST": mock_backend_auth_server["host"],
        "BACKEND_GRPC_PORT": str(mock_backend_auth_server["port"]),
        "RUST_LOG": "info",
    })

    # Start the pre-built binary directly (much faster than cargo run)
    log_file = log_path.open("w+b")
    process = subprocess.Popen(
        [str(rust_ingestion_binary)],
        cwd=INGESTION_DIR,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    # Wait for internal service to be ready (should be fast since binary is pre-built)
    if not wait_for_port(ingestion_internal_port, timeout=10.0):
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        log_file.flush()
        log_file.close()
        pytest.fail(
            "Rust ingestion service failed to start within 10s.\n"
            f"Log tail:\n{read_log_tail(log_path)}"
        )

    # Also ensure the public OTLP port is ready (some tests ingest spans).
    if not wait_for_port(ingestion_public_port, timeout=10.0):
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        log_file.flush()
        log_file.close()
        pytest.fail(
            "Rust ingestion service OTLP port failed to start within 10s.\n"
            f"Log tail:\n{read_log_tail(log_path)}"
        )

    logger.info(
        "Rust ingestion service started "
        f"(internal port: {ingestion_internal_port}, public port: {ingestion_public_port})"
    )

    failures_before = request.session.testsfailed
    yield {
        "process": process,
        "temp_dir": temp_dir,
        "wal_dir": wal_dir,
        "parquet_dir": parquet_dir,
        "snapshot_path": snapshot_path,
        "internal_port": ingestion_internal_port,
        "public_port": ingestion_public_port,
        "log_path": str(log_path),
    }

    # Cleanup
    logger.info("Stopping Rust ingestion service")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    log_file.flush()
    log_file.close()

    if request.session.testsfailed > failures_before:
        logger.error(
            "Rust ingestion test module failed; preserving diagnostics at "
            f"{temp_dir}\nLog tail:\n{read_log_tail(log_path)}"
        )
    else:
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            logger.warning(f"Failed to clean up temp dir: {e}")
