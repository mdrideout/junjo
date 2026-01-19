"""Pytest configuration and fixtures.

Provides test database setup with temporary SQLite files.

IMPORTANT: Environment variables must be set BEFORE importing app code.
The env var setup happens at module level, and app imports are deferred to
inside fixtures to ensure correct initialization order.
"""

import os
import tempfile
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Set test database paths BEFORE any app code gets imported
# This ensures db_config.py (which creates engine at import time) uses test location
#
# Note: If JUNJO_SQLITE_PATH is already set (e.g., from shell for gRPC tests),
# we respect that. Otherwise, create temp paths for unit/integration tests.
if "JUNJO_SQLITE_PATH" not in os.environ:
    _test_base_dir = tempfile.mkdtemp(prefix="junjo_test_")
    os.environ["JUNJO_SQLITE_PATH"] = f"{_test_base_dir}/test.db"


@pytest_asyncio.fixture(scope="function", autouse=True)
async def test_db(request):
    """Create test database in temporary directory for each test.

    Each test gets a completely isolated database file that is cleaned up after.

    Yields:
        async_sessionmaker: Session factory for test database
    """
    # Skip fixture for gRPC integration tests - they use the running server's DB
    # (which also uses the temp path set above, ensuring isolation)
    if "requires_grpc_server" in [marker.name for marker in request.node.iter_markers()]:
        yield None
        return
    # Import app code here (after env vars are set at module level)
    from app.db_sqlite import models  # noqa: F401
    from app.db_sqlite.base import Base

    # Create temporary database file
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    db_url = f"sqlite+aiosqlite:///{db_path}"

    # Create engine
    engine = create_async_engine(db_url, echo=False)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    async_session_test = async_sessionmaker(
        engine,
        expire_on_commit=False
    )

    # Override global session with test session
    import app.db_sqlite.db_config as db_config
    original_session = db_config.async_session
    original_engine = db_config.engine
    db_config.async_session = async_session_test
    db_config.engine = engine  # Also override engine for complete isolation

    yield async_session_test

    # Restore original session and engine
    db_config.async_session = original_session
    db_config.engine = original_engine

    # Cleanup
    await engine.dispose()

    # Remove temp database file
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
        os.rmdir(temp_dir)
    except Exception:
        pass  # Ignore cleanup errors


@pytest.fixture
def mock_authenticated_user():
    """Create a mock AuthenticatedUser for testing.

    Returns:
        AuthenticatedUser: Mock user with test email and session info
    """
    from app.features.auth.models import AuthenticatedUser

    return AuthenticatedUser(
        email="test@example.com",
        user_id="test_user_123",
        authenticated_at=datetime(2025, 1, 1, 12, 0, 0),
        session_id="test_session_abc123"
    )
