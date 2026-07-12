"""
Pytest fixtures for internal auth integration tests.

Provides shared test data and setup for gRPC integration tests.
These tests require starting the Python gRPC server.
"""

import asyncio
import os
import socket
import tempfile
import threading
import time
from datetime import datetime

import nanoid
import pytest
from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config.settings import settings
from app.db_sqlite.api_keys.repository import APIKeyRepository
from app.features.auth.models import AuthenticatedUser


def is_port_in_use(port: int) -> bool:
    """Check if a port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def wait_for_port(port: int, timeout: float = 10.0) -> bool:
    """Wait for a port to become available."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(0.1)
    return False


@pytest.fixture(scope="module")
def test_database():
    """Create an isolated test database for gRPC integration tests.

    This fixture creates a temporary SQLite database and overrides the
    global session factory so all database operations use the test database.
    """
    from app.db_sqlite import models  # noqa: F401
    from app.db_sqlite.base import Base

    # Create temporary database file
    temp_dir = tempfile.mkdtemp(prefix="grpc_test_")
    db_path = os.path.join(temp_dir, "test.db")
    db_url = f"sqlite+aiosqlite:///{db_path}"

    # Create engine and tables synchronously
    from sqlalchemy import create_engine

    sync_engine = create_engine(db_url.replace("+aiosqlite", ""))
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    # Create async engine and session factory
    engine = create_async_engine(db_url, echo=False)
    async_session_test = async_sessionmaker(engine, expire_on_commit=False)

    # Override global session with test session
    import app.db_sqlite.db_config as db_config

    original_session = db_config.async_session
    original_engine = db_config.engine
    db_config.async_session = async_session_test
    db_config.engine = engine

    logger.info(f"Test database created at {db_path}")

    yield {"db_path": db_path, "temp_dir": temp_dir}

    # Restore original session
    db_config.async_session = original_session
    db_config.engine = original_engine

    # Cleanup temp directory
    import shutil

    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass


@pytest.fixture(scope="module")
def grpc_server_for_tests(test_database):
    """Start the Python gRPC server for internal_auth tests.

    This fixture:
    1. Checks if a gRPC server is already running on the port
    2. If not, starts one in a background daemon thread
    3. Waits for the server to be ready

    The server runs as a daemon thread, so it will be automatically
    cleaned up when the test process exits.
    """
    from app.grpc_server import start_grpc_server_background

    # Check if server is already running
    if is_port_in_use(settings.GRPC_PORT):
        logger.info(f"gRPC server already running on port {settings.GRPC_PORT}")
        yield {"already_running": True}
        return

    # Start gRPC server in background thread
    async def start_server():
        await start_grpc_server_background()

    loop = asyncio.new_event_loop()

    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start_server())
        loop.run_forever()

    server_thread = threading.Thread(target=run_loop, daemon=True)
    server_thread.start()

    # Wait for server to start
    if not wait_for_port(settings.GRPC_PORT, timeout=10.0):
        pytest.skip(f"Failed to start gRPC server on port {settings.GRPC_PORT}")

    logger.info(f"gRPC server started on port {settings.GRPC_PORT}")

    yield {"already_running": False, "loop": loop, "thread": server_thread}

    # Don't explicitly stop - daemon thread will be cleaned up automatically


@pytest.fixture(scope="module")
def test_api_key(grpc_server_for_tests):
    """
    Create a test API key for gRPC integration tests.

    This fixture creates a single API key that's used across all integration tests
    in this module. The key is created once at the start and cleaned up at the end.

    Depends on grpc_server_for_tests which ensures the database is set up.

    Scope: module (shared across all tests in the file, created once)

    Returns:
        str: The 64-character test API key
    """
    # Generate a production-like API key
    key_id = nanoid.generate(size=21)
    api_key = nanoid.generate(size=64)

    # Create a mock authenticated user for the repository call
    mock_user = AuthenticatedUser(
        email="test@example.com",
        user_id="test_user_123",
        authenticated_at=datetime(2025, 1, 1, 12, 0, 0),
        session_id="test_session_abc123",
    )

    # Create the key in the database
    async def create_key():
        await APIKeyRepository.create(
            id=key_id, key=api_key, name="Integration Test Key", authenticated_user=mock_user
        )
        return api_key

    # Run the async function in a new event loop
    created_key = asyncio.run(create_key())

    logger.info(f"Created test API key: {key_id}")

    # Provide the key to tests
    yield created_key

    # Cleanup: Delete the key after tests complete
    async def cleanup():
        try:
            await APIKeyRepository.delete_by_id(key_id)
            logger.info(f"Cleaned up test API key: {key_id}")
        except Exception:
            # Key might not exist if test created/deleted it
            pass

    asyncio.run(cleanup())
