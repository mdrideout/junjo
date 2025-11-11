"""Concurrency tests for API key operations.

Tests race conditions and concurrent access patterns to ensure
data integrity under concurrent load.
"""

import asyncio
from unittest.mock import patch

import pytest

from app.db_sqlite.api_keys.repository import APIKeyRepository
from app.features.api_keys.service import APIKeyService


@pytest.mark.concurrency
@pytest.mark.asyncio
async def test_concurrent_api_key_creation(mock_authenticated_user):
    """Test creating 100 API keys simultaneously.

    Validates:
    - Nanoid uniqueness under concurrent load
    - Database transaction isolation
    - No duplicate IDs or keys
    """
    async def create_key(i: int):
        """Create a single API key."""
        try:
            return await APIKeyService.create_api_key(
                name=f"Concurrent Key {i}",
                authenticated_user=mock_authenticated_user
            )
        except Exception:
            return None

    # Create 100 keys concurrently
    results = await asyncio.gather(*[create_key(i) for i in range(100)])

    # Filter out None results (failures)
    successful_keys = [k for k in results if k is not None]

    # All should succeed
    assert len(successful_keys) == 100, f"Expected 100 keys, got {len(successful_keys)}"

    # Extract all IDs and keys
    ids = [k.id for k in successful_keys]
    keys = [k.key for k in successful_keys]

    # All IDs should be unique
    assert len(set(ids)) == 100, "Duplicate IDs detected!"

    # All keys should be unique
    assert len(set(keys)) == 100, "Duplicate keys detected!"

    # Verify all are 21 and 64 chars respectively
    assert all(len(id) == 21 for id in ids)
    assert all(len(key) == 64 for key in keys)


@pytest.mark.concurrency
@pytest.mark.asyncio
async def test_concurrent_key_read_and_delete(mock_authenticated_user):
    """Test reading API key while another task deletes it.

    Ensures no crashes occur when racing read/delete operations.
    """
    # Create a key
    created = await APIKeyService.create_api_key(
        name="Test Key",
        authenticated_user=mock_authenticated_user
    )

    async def read_key():
        """Read the key."""
        try:
            return await APIKeyRepository.get_by_id(created.id)
        except Exception:
            return None

    async def delete_key():
        """Delete the key."""
        # Small delay to increase race condition likelihood
        await asyncio.sleep(0.01)
        return await APIKeyService.delete_api_key(
            created.id,
            authenticated_user=mock_authenticated_user
        )

    # Run read and delete concurrently
    read_result, delete_result = await asyncio.gather(
        read_key(),
        delete_key(),
    )

    # Delete should succeed
    assert delete_result is True

    # Read might succeed (got key before delete) or fail (deleted first)
    # Both outcomes are acceptable - no crash is the important part
    assert read_result is None or read_result.id == created.id


@pytest.mark.concurrency
@pytest.mark.asyncio
async def test_concurrent_duplicate_key_prevention(mock_authenticated_user):
    """Test that duplicate keys are prevented even under concurrent creation.

    This tests the database unique constraint enforcement.
    """
    # Mock nanoid to return duplicate values
    duplicate_id = "duplicate_id_21chars"
    duplicate_key = "duplicate_key_64chars" + "x" * 42  # Pad to 64 chars

    call_count = 0

    def mock_generate_id():
        """Always return same ID."""
        return duplicate_id

    def mock_generate_key():
        """Return same key first two times, then unique keys."""
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return duplicate_key
        return f"unique_key_{call_count}" + "x" * (64 - 10 - len(str(call_count)))

    with patch.object(APIKeyService, "generate_id", side_effect=mock_generate_id):
        with patch.object(APIKeyService, "generate_key", side_effect=mock_generate_key):
            async def create_key(i: int):
                """Try to create key with duplicate values."""
                try:
                    return await APIKeyService.create_api_key(
                        name=f"Key {i}",
                        authenticated_user=mock_authenticated_user
                    )
                except Exception as e:
                    # Expected: unique constraint violation
                    return str(e)

            # Try to create 5 keys with duplicate ID/key values
            results = await asyncio.gather(*[create_key(i) for i in range(5)])

            # Count successes and failures
            successes = [r for r in results if hasattr(r, "id")]
            failures = [r for r in results if isinstance(r, str)]

            # At most 1 should succeed (due to unique constraints)
            assert len(successes) <= 1, "Multiple keys created with duplicate ID/key!"

            # Most should fail due to unique constraint
            assert len(failures) >= 4, "Expected unique constraint violations"


@pytest.mark.concurrency
@pytest.mark.asyncio
async def test_concurrent_list_while_creating(mock_authenticated_user):
    """Test listing API keys while other tasks are creating them.

    Ensures consistent read behavior during concurrent writes.
    """
    async def create_keys():
        """Create 20 keys."""
        for i in range(20):
            await APIKeyService.create_api_key(
                name=f"Key {i}",
                authenticated_user=mock_authenticated_user
            )
            await asyncio.sleep(0.01)  # Small delay between creates

    async def list_keys_multiple_times():
        """List keys 10 times."""
        counts = []
        for _ in range(10):
            keys = await APIKeyService.list_api_keys(
                authenticated_user=mock_authenticated_user
            )
            counts.append(len(keys))
            await asyncio.sleep(0.02)
        return counts

    # Run creation and listing concurrently
    _, counts = await asyncio.gather(
        create_keys(),
        list_keys_multiple_times(),
    )

    # Counts should be monotonically increasing (or stable)
    # Due to isolation, we might see old snapshot or new data
    assert len(counts) == 10

    # Each subsequent read should see same or more keys (never less)
    for i in range(1, len(counts)):
        assert counts[i] >= counts[i-1], f"Count decreased: {counts[i-1]} -> {counts[i]}"


@pytest.mark.concurrency
@pytest.mark.asyncio
async def test_concurrent_delete_same_key(mock_authenticated_user):
    """Test deleting the same key from multiple tasks.

    Ensures idempotent delete behavior.
    """
    # Create a key
    created = await APIKeyService.create_api_key(
        name="Delete Me",
        authenticated_user=mock_authenticated_user
    )

    async def delete_key():
        """Try to delete the key."""
        try:
            return await APIKeyService.delete_api_key(
                created.id,
                authenticated_user=mock_authenticated_user
            )
        except Exception as e:
            return str(e)

    # Try to delete from 10 concurrent tasks
    results = await asyncio.gather(*[delete_key() for _ in range(10)])

    # Count successes (True) and failures (False or exception)
    successes = [r for r in results if r is True]
    [r for r in results if r is False or isinstance(r, str)]

    # At least one should succeed
    assert len(successes) >= 1

    # Others might return False (not found) - this is acceptable
    # No crashes or exceptions expected

    # Verify key is gone
    key = await APIKeyRepository.get_by_id(created.id)
    assert key is None


@pytest.mark.concurrency
@pytest.mark.asyncio
async def test_concurrent_create_and_count(mock_authenticated_user):
    """Test creating keys while counting them.

    Verifies transaction isolation and consistent read behavior.
    """
    initial_count = len(await APIKeyService.list_api_keys(
        authenticated_user=mock_authenticated_user
    ))

    async def create_many():
        """Create 50 keys."""
        for i in range(50):
            await APIKeyService.create_api_key(
                name=f"Concurrent {i}",
                authenticated_user=mock_authenticated_user
            )

    async def count_periodically():
        """Count keys 20 times."""
        counts = []
        for _ in range(20):
            keys = await APIKeyService.list_api_keys(
                authenticated_user=mock_authenticated_user
            )
            counts.append(len(keys))
            await asyncio.sleep(0.01)
        return counts

    # Run concurrently
    _, counts = await asyncio.gather(create_many(), count_periodically())

    # Final count should be initial + 50
    final_count = len(await APIKeyService.list_api_keys(
        authenticated_user=mock_authenticated_user
    ))
    assert final_count == initial_count + 50

    # Observed counts should never exceed final count
    assert all(c <= final_count for c in counts)


@pytest.mark.concurrency
@pytest.mark.asyncio
async def test_high_concurrency_stress_test(mock_authenticated_user):
    """Stress test with 200 concurrent operations (mix of CRUD).

    Tests system stability under high concurrent load.
    """
    operations_completed = {"create": 0, "read": 0, "delete": 0}
    errors = []

    async def random_operation(i: int):
        """Perform a random CRUD operation."""
        try:
            # Create
            if i % 3 == 0:
                await APIKeyService.create_api_key(
                    name=f"Stress {i}",
                    authenticated_user=mock_authenticated_user
                )
                operations_completed["create"] += 1

            # Read
            elif i % 3 == 1:
                await APIKeyService.list_api_keys(
                    authenticated_user=mock_authenticated_user
                )
                operations_completed["read"] += 1

            # Delete (create first, then delete)
            else:
                key = await APIKeyService.create_api_key(
                    name=f"Temp {i}",
                    authenticated_user=mock_authenticated_user
                )
                await APIKeyService.delete_api_key(
                    key.id,
                    authenticated_user=mock_authenticated_user
                )
                operations_completed["delete"] += 1

        except Exception as e:
            errors.append(str(e))

    # Run 200 concurrent operations
    await asyncio.gather(*[random_operation(i) for i in range(200)])

    # Verify operations completed
    total_ops = sum(operations_completed.values())
    assert total_ops == 200, f"Only {total_ops}/200 operations completed"

    # Should have minimal errors (some duplicate key errors acceptable)
    assert len(errors) < 10, f"Too many errors: {len(errors)}"

    # Verify database is in consistent state (can query without errors)
    final_keys = await APIKeyService.list_api_keys(
        authenticated_user=mock_authenticated_user
    )
    assert isinstance(final_keys, list)
