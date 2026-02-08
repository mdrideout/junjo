"""Pytest fixtures for backend integration tests.

Provides shared fixtures for tests that require the Rust ingestion service.
"""

import os
import shutil
import signal
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
INGESTION_INTERNAL_PORT = 50052  # Internal gRPC port for WAL reads
INGESTION_PUBLIC_PORT = 50051  # Public port for span ingestion


def is_port_in_use(port: int) -> bool:
    """Check if a port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def kill_existing_ingestion_processes():
    """Kill any existing ingestion service processes on the gRPC ports."""
    for port in [INGESTION_INTERNAL_PORT, INGESTION_PUBLIC_PORT]:
        try:
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
            subprocess.run(["pkill", "-9", "-f", "ingestion"], capture_output=True)
            break
    time.sleep(0.5)


def wait_for_port(port: int, timeout: float = 60.0) -> bool:
    """Wait for a port to become available."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(0.1)
    return False


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
def rust_ingestion_service(rust_ingestion_binary, mock_backend_auth_server):
    """Start the Rust ingestion service for integration tests.

    This fixture:
    1. Uses pre-built binary from rust_ingestion_binary (session-scoped)
    2. Kills any existing ingestion processes
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
    # Kill existing processes
    kill_existing_ingestion_processes()

    # Ensure ports are free
    for port in [INGESTION_INTERNAL_PORT, INGESTION_PUBLIC_PORT]:
        if is_port_in_use(port):
            pytest.skip(f"Port {port} still in use after killing processes")

    # Create temp directories
    temp_dir = tempfile.mkdtemp(prefix="rust_ingestion_test_")
    wal_dir = os.path.join(temp_dir, "wal")
    parquet_dir = os.path.join(temp_dir, "parquet")
    snapshot_path = os.path.join(temp_dir, "hot_snapshot.parquet")
    os.makedirs(wal_dir, exist_ok=True)
    os.makedirs(parquet_dir, exist_ok=True)

    logger.info(f"Starting Rust ingestion service with temp dir: {temp_dir}")

    # Set environment for the service
    env = os.environ.copy()
    env.update({
        "WAL_DIR": wal_dir,
        "SNAPSHOT_PATH": snapshot_path,
        "PARQUET_OUTPUT_DIR": parquet_dir,
        "GRPC_PORT": str(INGESTION_PUBLIC_PORT),
        "INTERNAL_GRPC_PORT": str(INGESTION_INTERNAL_PORT),
        # Provide a tiny in-process backend auth gRPC so OTLP ingest can validate API keys.
        "BACKEND_GRPC_HOST": mock_backend_auth_server["host"],
        "BACKEND_GRPC_PORT": str(mock_backend_auth_server["port"]),
        "RUST_LOG": "info",
    })

    # Start the pre-built binary directly (much faster than cargo run)
    process = subprocess.Popen(
        [str(rust_ingestion_binary)],
        cwd=INGESTION_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for internal service to be ready (should be fast since binary is pre-built)
    if not wait_for_port(INGESTION_INTERNAL_PORT, timeout=10.0):
        try:
            stdout, stderr = process.communicate(timeout=5)
            error_msg = f"stdout: {stdout.decode()}\nstderr: {stderr.decode()}"
        except subprocess.TimeoutExpired:
            process.kill()
            error_msg = "Process timed out"
        pytest.fail(f"Rust ingestion service failed to start within 10s.\n{error_msg}")

    # Also ensure the public OTLP port is ready (some tests ingest spans).
    if not wait_for_port(INGESTION_PUBLIC_PORT, timeout=10.0):
        try:
            stdout, stderr = process.communicate(timeout=5)
            error_msg = f"stdout: {stdout.decode()}\nstderr: {stderr.decode()}"
        except subprocess.TimeoutExpired:
            process.kill()
            error_msg = "Process timed out"
        pytest.fail(
            f"Rust ingestion service OTLP port failed to start within 10s.\n{error_msg}"
        )

    logger.info(f"Rust ingestion service started (internal port: {INGESTION_INTERNAL_PORT})")

    yield {
        "process": process,
        "temp_dir": temp_dir,
        "wal_dir": wal_dir,
        "parquet_dir": parquet_dir,
        "snapshot_path": snapshot_path,
        "internal_port": INGESTION_INTERNAL_PORT,
        "public_port": INGESTION_PUBLIC_PORT,
    }

    # Cleanup
    logger.info("Stopping Rust ingestion service")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()

    # Clean up temp directory
    try:
        shutil.rmtree(temp_dir)
    except Exception as e:
        logger.warning(f"Failed to clean up temp dir: {e}")
