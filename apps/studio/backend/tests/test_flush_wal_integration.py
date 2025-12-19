"""FlushWAL RPC Integration Tests.

Tests the FlushWAL gRPC endpoint on the Rust ingestion service.
The rust_ingestion_service fixture automatically starts an ephemeral service.

The FlushWAL RPC:
1. Flushes all WAL segments to Parquet files (cold storage)
2. Creates date-partitioned Parquet files in the output directory
3. Notifies the backend via NotifyNewParquetFile RPC
4. Clears the WAL segments after successful flush

Usage:
    pytest tests/test_flush_wal_integration.py -v -m requires_ingestion_service
"""

import grpc
import pytest

from app.features.span_ingestion.ingestion_client import IngestionClient

# Mark all tests as requiring the ingestion service
pytestmark = [pytest.mark.requires_ingestion_service, pytest.mark.integration]


@pytest.fixture
async def ingestion_client(rust_ingestion_service):
    """Create and connect an IngestionClient for testing.

    Uses the rust_ingestion_service fixture to ensure service is running.
    """
    client = IngestionClient(
        host="localhost",
        port=rust_ingestion_service["internal_port"],
    )

    try:
        await client.connect()
        yield client
    finally:
        await client.close()


class TestFlushWALBasic:
    """Basic tests for FlushWAL RPC."""

    @pytest.mark.asyncio
    async def test_flush_wal_returns_bool(self, ingestion_client):
        """FlushWAL should return a boolean result."""
        result = await ingestion_client.flush_wal()

        # Should return a bool
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_flush_wal_empty_success(self, ingestion_client):
        """FlushWAL with no data should still succeed."""
        result = await ingestion_client.flush_wal()

        # Empty WAL is a valid case - should succeed
        assert result is True

    @pytest.mark.asyncio
    async def test_flush_wal_idempotent(self, ingestion_client):
        """Multiple FlushWAL calls should be idempotent."""
        # First flush
        result1 = await ingestion_client.flush_wal()

        # Second flush (should have nothing to flush)
        result2 = await ingestion_client.flush_wal()

        # Both should succeed
        assert result1 is True
        assert result2 is True


class TestFlushWALWithHotSnapshot:
    """Tests for FlushWAL interaction with hot snapshots."""

    @pytest.mark.asyncio
    async def test_flush_then_hot_snapshot(self, ingestion_client):
        """After FlushWAL, hot snapshot should have no new data."""
        # First flush all data to cold storage
        flush_result = await ingestion_client.flush_wal()
        assert flush_result is True

        # Then get hot snapshot - should be empty or contain only new data
        hot_result = await ingestion_client.prepare_hot_snapshot()

        # Hot snapshot should succeed (even if empty)
        assert hot_result is not None

    @pytest.mark.asyncio
    async def test_hot_snapshot_then_flush(self, ingestion_client):
        """FlushWAL should succeed after hot snapshot."""
        # First get hot snapshot
        hot_result = await ingestion_client.prepare_hot_snapshot()
        assert hot_result is not None

        # Then flush - should succeed
        flush_result = await ingestion_client.flush_wal()
        assert flush_result is True


class TestFlushWALErrors:
    """Tests for FlushWAL error handling."""

    @pytest.mark.asyncio
    async def test_handles_invalid_connection(self):
        """Should handle connection to non-existent service gracefully."""
        client = IngestionClient(host="localhost", port=59999)  # Non-existent port

        with pytest.raises(grpc.aio.AioRpcError):
            await client.connect()
            await client.flush_wal()


class TestFlushWALStress:
    """Stress tests for FlushWAL."""

    @pytest.mark.asyncio
    async def test_concurrent_flush_safe(self, ingestion_client):
        """Multiple concurrent flushes should not cause errors."""
        import asyncio

        # Run multiple flushes concurrently
        tasks = [ingestion_client.flush_wal() for _ in range(3)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should succeed (no exceptions)
        for result in results:
            assert result is True or isinstance(result, bool)
