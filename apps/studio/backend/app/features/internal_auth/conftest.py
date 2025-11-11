"""
Pytest fixtures for internal auth integration tests.

Provides shared test data and setup for gRPC integration tests.
"""

import asyncio
from datetime import datetime

import nanoid
import pytest

from app.db_sqlite.api_keys.repository import APIKeyRepository
from app.features.auth.models import AuthenticatedUser


@pytest.fixture(scope="module")
def test_api_key():
    """
    Create a test API key for gRPC integration tests.

    This fixture creates a single API key that's used across all integration tests
    in this module. The key is created once at the start and cleaned up at the end.

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

    # Create the key in the database synchronously
    async def create_key():
        await APIKeyRepository.create(
            id=key_id, key=api_key, name="Integration Test Key", authenticated_user=mock_user
        )
        return api_key

    # Run the async function
    created_key = asyncio.run(create_key())

    # Provide the key to tests
    yield created_key

    # Cleanup: Delete the key after tests complete
    async def cleanup():
        try:
            await APIKeyRepository.delete_by_id(key_id)
        except Exception:
            # Key might not exist if test created/deleted it
            pass

    asyncio.run(cleanup())
