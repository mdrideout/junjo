"""gRPC client for Rust ingestion service.

This client connects to the ingestion service and provides:
1. Hot snapshot preparation for DataFusion queries
2. Manual WAL flush trigger

The backend reads snapshot files directly via DataFusion rather than
streaming Arrow IPC data over gRPC.
"""

from dataclasses import dataclass

import grpc
from loguru import logger

from app.config.settings import settings
from app.proto_gen import ingestion_pb2, ingestion_pb2_grpc


@dataclass
class HotSnapshotResult:
    """Result from PrepareHotSnapshot RPC."""

    snapshot_path: str  # Path to stable Parquet file
    row_count: int  # Number of spans in snapshot
    file_size_bytes: int  # File size for logging
    recent_cold_paths: list[str]  # Recently flushed cold Parquet files (may not be indexed yet)
    success: bool
    error_message: str


class IngestionClient:
    """Async gRPC client for Rust ingestion service.

    This client connects to the ingestion service's InternalIngestionService
    and provides methods to prepare hot snapshots and trigger flushes.

    Usage:
        client = IngestionClient()
        await client.connect()
        try:
            result = await client.prepare_hot_snapshot()
            # Read result.snapshot_path via DataFusion...
        finally:
            await client.close()
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
    ):
        """Initialize ingestion client.

        Args:
            host: Ingestion service hostname (default from settings)
            port: Ingestion service port (default from settings)
        """
        self.host = host or settings.span_ingestion.host
        self.port = port or settings.span_ingestion.port
        self.address = f"{self.host}:{self.port}"
        self.channel: grpc.aio.Channel | None = None
        self.stub: ingestion_pb2_grpc.InternalIngestionServiceStub | None = None

    async def connect(self) -> None:
        """Connect to ingestion service.

        Creates an insecure gRPC channel and stub. This is safe because
        the ingestion service is internal (not exposed to internet).
        """
        try:
            self.channel = grpc.aio.insecure_channel(
                self.address,
                options=[
                    # Keepalive settings
                    ("grpc.keepalive_time_ms", 300000),  # 5 minutes
                    ("grpc.keepalive_timeout_ms", 20000),  # 20 seconds
                    ("grpc.keepalive_permit_without_calls", 0),
                ],
            )
            self.stub = ingestion_pb2_grpc.InternalIngestionServiceStub(self.channel)
            logger.info(f"Connected to ingestion service at {self.address}")
        except Exception as e:
            logger.error(
                "Failed to connect to ingestion service",
                extra={"error": str(e), "error_type": type(e).__name__, "address": self.address},
            )
            raise

    async def close(self) -> None:
        """Close gRPC channel and cleanup resources."""
        if self.channel:
            await self.channel.close()
            logger.info("Closed ingestion service connection")

    async def prepare_hot_snapshot(self) -> HotSnapshotResult:
        """Prepare a hot snapshot file for DataFusion queries.

        This calls PrepareHotSnapshot RPC which:
        1. Flushes any pending in-memory spans to IPC segments
        2. Creates a stable Parquet snapshot of all WAL data
        3. Returns the file path for direct reading

        Returns:
            HotSnapshotResult with snapshot_path if successful

        Raises:
            grpc.aio.AioRpcError: If gRPC call fails
            Exception: If stub not initialized
        """
        if not self.stub:
            raise Exception("Client not connected. Call connect() first.")

        request = ingestion_pb2.PrepareHotSnapshotRequest()

        try:
            response = await self.stub.PrepareHotSnapshot(request)

            result = HotSnapshotResult(
                snapshot_path=response.snapshot_path,
                row_count=response.row_count,
                file_size_bytes=response.file_size_bytes,
                recent_cold_paths=list(response.recent_cold_paths),
                success=response.success,
                error_message=response.error_message,
            )

            if result.success:
                logger.debug(
                    "Hot snapshot prepared",
                    extra={
                        "snapshot_path": result.snapshot_path,
                        "row_count": result.row_count,
                        "file_size_bytes": result.file_size_bytes,
                    },
                )
            else:
                logger.warning(
                    "Hot snapshot preparation failed",
                    extra={"error_message": result.error_message},
                )

            return result

        except grpc.aio.AioRpcError as e:
            logger.error(
                "gRPC error preparing hot snapshot",
                extra={"code": str(e.code()), "details": e.details()},
            )
            raise

    async def flush_wal(self) -> bool:
        """Trigger manual WAL flush to Parquet files.

        This calls the FlushWAL RPC to immediately flush any pending
        WAL data to cold Parquet files.

        Returns:
            True if flush succeeded, False otherwise

        Raises:
            grpc.aio.AioRpcError: If gRPC call fails
            Exception: If stub not initialized
        """
        if not self.stub:
            raise Exception("Client not connected. Call connect() first.")

        request = ingestion_pb2.FlushWALRequest()

        try:
            response = await self.stub.FlushWAL(request)

            if response.success:
                logger.info("WAL flush completed successfully")
            else:
                logger.error(
                    "WAL flush failed",
                    extra={"error_message": response.error_message},
                )

            return response.success

        except grpc.aio.AioRpcError as e:
            logger.error(
                "gRPC error flushing WAL",
                extra={"code": str(e.code()), "details": e.details()},
            )
            raise
