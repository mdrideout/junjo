"""gRPC client for ingestion service span reading and WAL queries.

This client connects to the ingestion service and provides:
1. Span reading from SQLite WAL using server-streaming gRPC (for V3 flusher)
2. WAL query operations for unified DataFusion queries (V4 - Arrow IPC)

Port of: backend/ingestion_client/client.go
"""

from dataclasses import dataclass

import grpc
import pyarrow as pa
from loguru import logger

from app.config.settings import settings
from app.proto_gen import ingestion_pb2, ingestion_pb2_grpc


@dataclass
class SpanWithResource:
    """Container for span data from ingestion service.

    Matches Go struct: backend/ingestion_client/client.go:15-19
    """

    key_ulid: bytes  # ULID key for ordering/resumption
    span_bytes: bytes  # Serialized OTLP Span protobuf
    resource_bytes: bytes  # Serialized OTLP Resource protobuf


class IngestionClient:
    """Async gRPC client for reading spans from ingestion service.

    This client connects to the ingestion service's InternalIngestionService
    and provides methods to read spans from the SQLite WAL.

    Usage:
        client = IngestionClient()
        await client.connect()
        try:
            spans = await client.read_spans(last_key, batch_size=100)
            # Process spans...
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
        self.host = host or settings.span_ingestion.INGESTION_HOST
        self.port = port or settings.span_ingestion.INGESTION_PORT
        self.address = f"{self.host}:{self.port}"
        self.channel: grpc.aio.Channel | None = None
        self.stub: ingestion_pb2_grpc.InternalIngestionServiceStub | None = None

    async def connect(self) -> None:
        """Connect to ingestion service.

        Creates an insecure gRPC channel and stub. This is safe because
        the ingestion service is internal (not exposed to internet).

        Raises:
            Exception: If connection fails
        """
        try:
            self.channel = grpc.aio.insecure_channel(
                self.address,
                options=[
                    ("grpc.keepalive_time_ms", 10000),
                    ("grpc.keepalive_timeout_ms", 5000),
                    ("grpc.keepalive_permit_without_calls", 1),
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

    async def read_spans(
        self, start_key: bytes, batch_size: int = 100
    ) -> tuple[list[SpanWithResource], int]:
        """Read spans from ingestion service starting after start_key.

        This calls the ReadSpans RPC which returns a server-streaming response.
        The method collects all spans from the stream and returns them as a list,
        along with the count of remaining unretrieved spans.

        Args:
            start_key: ULID key to start after (empty bytes = start from beginning)
            batch_size: Maximum number of spans to return

        Returns:
            Tuple of (spans, remaining_count):
                - spans: List of SpanWithResource objects containing span data
                - remaining_count: Number of unretrieved spans remaining in WAL

        Raises:
            grpc.aio.AioRpcError: If gRPC call fails
            Exception: If stub not initialized (call connect() first)

        Reference: backend/ingestion_client/client.go:48-77
        """
        if not self.stub:
            raise Exception("Client not connected. Call connect() first.")

        request = ingestion_pb2.ReadSpansRequest(start_key_ulid=start_key, batch_size=batch_size)

        spans = []
        remaining_count = 0
        last_key_processed = None
        try:
            # Server-streaming RPC: iterate over responses
            # The server sends span messages followed by a final count message
            async for response in self.stub.ReadSpans(request):
                # Check if this is a span message or the final count/cursor message
                if response.span_bytes and response.resource_bytes:
                    # This is a span message
                    spans.append(
                        SpanWithResource(
                            key_ulid=response.key_ulid,
                            span_bytes=response.span_bytes,
                            resource_bytes=response.resource_bytes,
                        )
                    )
                else:
                    # This is the final message with remaining_count and last key processed
                    # The key_ulid may be set to help advance cursor past corrupted spans
                    remaining_count = response.remaining_count
                    if response.key_ulid:
                        last_key_processed = response.key_ulid

            # If we received spans, log success
            # Otherwise, use the last_key_processed from the final message (may skip corrupted spans)
            if spans:
                logger.debug(
                    f"Read {len(spans)} spans from ingestion service",
                    extra={
                        "batch_size": batch_size,
                        "received": len(spans),
                        "remaining_count": remaining_count,
                    },
                )
            elif last_key_processed:
                # No spans succeeded, but we have a cursor to advance past corruption
                logger.warning(
                    "No spans received but cursor advanced (likely corrupted spans skipped)",
                    extra={
                        "remaining_count": remaining_count,
                        "last_key_processed": last_key_processed.hex(),
                    },
                )
                # Create a dummy span entry with just the key so backend can update cursor
                spans.append(
                    SpanWithResource(
                        key_ulid=last_key_processed,
                        span_bytes=b"",  # Empty - will be filtered out by backend
                        resource_bytes=b"",
                    )
                )
            else:
                logger.debug(
                    "No new spans available from ingestion service",
                    extra={"remaining_count": remaining_count},
                )

            return spans, remaining_count

        except grpc.aio.AioRpcError as e:
            logger.error(
                "gRPC error reading spans",
                extra={
                    "code": str(e.code()),
                    "details": e.details(),
                    "error_type": type(e).__name__,
                },
            )
            raise
        except Exception as e:
            logger.error(
                "Unexpected error reading spans",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            raise

    # =========================================================================
    # WAL Query Methods (V4 Unified DataFusion Queries - Arrow IPC)
    # =========================================================================

    async def get_wal_spans_arrow(
        self,
        *,
        trace_id: str | None = None,
        service_name: str | None = None,
        root_only: bool = False,
        workflow_only: bool = False,
        limit: int = 0,
    ) -> pa.Table:
        """Get spans from WAL as Arrow Table.

        This is the unified WAL query method that returns spans as Arrow IPC data.
        The returned Table can be registered with DataFusion for unified SQL queries.

        Args:
            trace_id: Filter by trace ID (exact match)
            service_name: Filter by service name (exact match)
            root_only: Only return root spans (no parent)
            workflow_only: Only return workflow spans (junjo.span_type = 'workflow')
            limit: Maximum number of spans to return (0 = no limit)

        Returns:
            PyArrow Table containing WAL spans

        Raises:
            grpc.aio.AioRpcError: If gRPC call fails
            Exception: If stub not initialized
        """
        if not self.stub:
            raise Exception("Client not connected. Call connect() first.")

        request = ingestion_pb2.GetWALSpansArrowRequest(
            root_only=root_only,
            workflow_only=workflow_only,
            limit=limit,
        )
        # Set optional fields only if provided
        if trace_id is not None:
            request.trace_id = trace_id
        if service_name is not None:
            request.service_name = service_name

        batches: list[pa.RecordBatch] = []
        total_rows = 0

        try:
            async for arrow_batch in self.stub.GetWALSpansArrow(request):
                if arrow_batch.ipc_bytes:
                    # Deserialize Arrow IPC bytes to RecordBatch
                    reader = pa.ipc.open_stream(arrow_batch.ipc_bytes)
                    # Read all batches from the IPC stream
                    for batch in reader:
                        batches.append(batch)
                        total_rows += batch.num_rows

            logger.debug(
                "Retrieved WAL spans as Arrow",
                extra={
                    "trace_id": trace_id,
                    "service_name": service_name,
                    "root_only": root_only,
                    "workflow_only": workflow_only,
                    "row_count": total_rows,
                },
            )

            # Combine all batches into a single Table
            if batches:
                return pa.Table.from_batches(batches)
            else:
                # Return empty table with expected schema
                return pa.table({})

        except grpc.aio.AioRpcError as e:
            logger.error(
                "gRPC error getting WAL spans as Arrow",
                extra={
                    "trace_id": trace_id,
                    "service_name": service_name,
                    "code": str(e.code()),
                    "details": e.details(),
                },
            )
            raise

    async def get_wal_distinct_service_names(self) -> list[str]:
        """Get all distinct service names currently in the WAL.

        Used to merge with Parquet-indexed services for complete listing.

        Returns:
            List of service name strings

        Raises:
            grpc.aio.AioRpcError: If gRPC call fails
            Exception: If stub not initialized
        """
        if not self.stub:
            raise Exception("Client not connected. Call connect() first.")

        request = ingestion_pb2.GetWALDistinctServiceNamesRequest()

        try:
            response = await self.stub.GetWALDistinctServiceNames(request)
            services = list(response.service_names)

            logger.debug(
                f"Retrieved {len(services)} distinct service names from WAL",
                extra={"count": len(services)},
            )
            return services

        except grpc.aio.AioRpcError as e:
            logger.error(
                "gRPC error getting WAL distinct service names",
                extra={"code": str(e.code()), "details": e.details()},
            )
            raise

    async def flush_wal(self) -> bool:
        """Trigger manual WAL flush to Parquet files.

        This calls the FlushWAL RPC to immediately flush any pending
        WAL data to Parquet files. Useful for testing or ensuring
        data is persisted before shutdown.

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
