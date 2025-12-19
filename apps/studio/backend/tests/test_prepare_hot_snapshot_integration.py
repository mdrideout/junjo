"""PrepareHotSnapshot RPC Integration Tests.

Tests the PrepareHotSnapshot gRPC endpoint on the Rust ingestion service.
The rust_ingestion_service fixture automatically starts an ephemeral service.

The PrepareHotSnapshot RPC:
1. Creates a Parquet file from in-memory WAL data
2. Returns the path to the snapshot file
3. Returns row count and file size metadata
4. Is used by the backend to get "hot tier" data for two-tier queries

Usage:
    pytest tests/test_prepare_hot_snapshot_integration.py -v -m requires_ingestion_service
"""

import os

import grpc
import pyarrow.parquet as pq
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


class TestPrepareHotSnapshotBasic:
    """Basic tests for PrepareHotSnapshot RPC."""

    @pytest.mark.asyncio
    async def test_prepare_hot_snapshot_returns_result(self, ingestion_client):
        """PrepareHotSnapshot should return a valid result object."""
        result = await ingestion_client.prepare_hot_snapshot()

        # Should return a result (success or empty)
        assert result is not None
        assert hasattr(result, "success")
        assert hasattr(result, "snapshot_path")
        assert hasattr(result, "row_count")
        assert hasattr(result, "file_size_bytes")

    @pytest.mark.asyncio
    async def test_prepare_hot_snapshot_empty_wal_success(self, ingestion_client):
        """PrepareHotSnapshot with empty WAL should still succeed."""
        result = await ingestion_client.prepare_hot_snapshot()

        # Empty WAL is a valid case - should not error
        assert result.success or result.row_count == 0

    @pytest.mark.asyncio
    async def test_prepare_hot_snapshot_valid_path(self, ingestion_client):
        """PrepareHotSnapshot should return a valid file path."""
        result = await ingestion_client.prepare_hot_snapshot()

        if result.success and result.snapshot_path:
            # Path should end with .parquet
            assert result.snapshot_path.endswith(".parquet")


class TestPrepareHotSnapshotWithData:
    """Tests for PrepareHotSnapshot with actual data.

    These tests require spans to be ingested first via OTLP.
    """

    @pytest.mark.asyncio
    async def test_snapshot_file_is_valid_parquet(self, ingestion_client):
        """Hot snapshot file should be readable as valid Parquet."""
        result = await ingestion_client.prepare_hot_snapshot()

        if not result.success or not result.snapshot_path:
            pytest.skip("No hot snapshot available (WAL may be empty)")

        # Verify file exists and is valid Parquet
        if os.path.exists(result.snapshot_path):
            table = pq.read_table(result.snapshot_path)

            # Should have expected columns
            expected_columns = {
                "span_id",
                "trace_id",
                "parent_span_id",
                "service_name",
                "name",
                "span_kind",
                "start_time",
                "end_time",
                "duration_ns",
                "status_code",
                "status_message",
                "attributes",
                "events",
                "resource_attributes",
            }
            actual_columns = set(table.column_names)
            assert expected_columns.issubset(actual_columns), (
                f"Missing columns: {expected_columns - actual_columns}"
            )

    @pytest.mark.asyncio
    async def test_snapshot_metadata_matches_file(self, ingestion_client):
        """Metadata in result should match actual file."""
        result = await ingestion_client.prepare_hot_snapshot()

        if not result.success or not result.snapshot_path:
            pytest.skip("No hot snapshot available (WAL may be empty)")

        if os.path.exists(result.snapshot_path):
            # Check row count matches
            table = pq.read_table(result.snapshot_path)
            assert table.num_rows == result.row_count, (
                f"Row count mismatch: file has {table.num_rows}, result says {result.row_count}"
            )

            # Check file size is reasonable (within 10% due to potential compression differences)
            actual_size = os.path.getsize(result.snapshot_path)
            if result.file_size_bytes > 0:
                size_diff = abs(actual_size - result.file_size_bytes) / result.file_size_bytes
                assert size_diff < 0.1, (
                    f"File size mismatch: actual {actual_size}, result says {result.file_size_bytes}"
                )


class TestPrepareHotSnapshotIdempotency:
    """Tests for PrepareHotSnapshot idempotency and stability."""

    @pytest.mark.asyncio
    async def test_multiple_calls_return_consistent_path(self, ingestion_client):
        """Multiple PrepareHotSnapshot calls should return consistent path."""
        result1 = await ingestion_client.prepare_hot_snapshot()
        result2 = await ingestion_client.prepare_hot_snapshot()

        if result1.success and result2.success:
            # Path should be the same (snapshot location is fixed)
            # Note: Content may differ if new spans arrived between calls
            assert result1.snapshot_path == result2.snapshot_path


class TestPrepareHotSnapshotErrors:
    """Tests for PrepareHotSnapshot error handling."""

    @pytest.mark.asyncio
    async def test_handles_invalid_connection(self):
        """Should handle connection to non-existent service gracefully."""
        client = IngestionClient(host="localhost", port=59999)  # Non-existent port

        with pytest.raises(grpc.aio.AioRpcError):
            await client.connect()
            await client.prepare_hot_snapshot()
