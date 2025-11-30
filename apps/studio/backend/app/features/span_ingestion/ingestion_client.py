"""gRPC client for ingestion service span reading and WAL queries.

This client connects to the ingestion service and provides:
1. Span reading from SQLite WAL using server-streaming gRPC (for V3 flusher)
2. WAL query operations for fusion queries (V4 - combining hot WAL + cold Parquet)

Port of: backend/ingestion_client/client.go
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import grpc
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
    # WAL Query Methods (V4 Fusion Queries)
    # =========================================================================

    async def get_wal_spans_by_trace_id(self, trace_id: str) -> list[dict[str, Any]]:
        """Get all spans from WAL matching a trace ID.

        Used for fusion queries combining WAL and Parquet data.

        Args:
            trace_id: The trace ID to query (hex string)

        Returns:
            List of span dictionaries in API response format

        Raises:
            grpc.aio.AioRpcError: If gRPC call fails
            Exception: If stub not initialized
        """
        if not self.stub:
            raise Exception("Client not connected. Call connect() first.")

        request = ingestion_pb2.GetWALSpansByTraceIdRequest(trace_id=trace_id)

        spans = []
        try:
            async for span_data in self.stub.GetWALSpansByTraceId(request):
                span_dict = _convert_span_data_to_api_format(span_data)
                spans.append(span_dict)

            logger.debug(
                f"Got {len(spans)} spans from WAL for trace",
                extra={"trace_id": trace_id, "count": len(spans)},
            )
            return spans

        except grpc.aio.AioRpcError as e:
            logger.error(
                "gRPC error getting WAL spans by trace_id",
                extra={
                    "trace_id": trace_id,
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

    async def get_wal_root_spans(self, service_name: str, limit: int = 500) -> list[dict[str, Any]]:
        """Get root spans (no parent) from the WAL for a service.

        Used for trace listing, merged with Parquet root spans.

        Args:
            service_name: Service to filter by
            limit: Maximum number of spans to return

        Returns:
            List of span dictionaries in API response format

        Raises:
            grpc.aio.AioRpcError: If gRPC call fails
            Exception: If stub not initialized
        """
        if not self.stub:
            raise Exception("Client not connected. Call connect() first.")

        request = ingestion_pb2.GetWALRootSpansRequest(service_name=service_name, limit=limit)

        spans = []
        try:
            async for span_data in self.stub.GetWALRootSpans(request):
                span_dict = _convert_span_data_to_api_format(span_data)
                spans.append(span_dict)

            logger.debug(
                f"Retrieved {len(spans)} root spans from WAL",
                extra={"service_name": service_name, "count": len(spans), "limit": limit},
            )
            return spans

        except grpc.aio.AioRpcError as e:
            logger.error(
                "gRPC error getting WAL root spans",
                extra={
                    "service_name": service_name,
                    "code": str(e.code()),
                    "details": e.details(),
                },
            )
            raise


def _convert_span_data_to_api_format(span_data: ingestion_pb2.SpanData) -> dict[str, Any]:
    """Convert gRPC SpanData to API response format.

    This matches the format returned by datafusion_query.py for Parquet spans.
    """
    # Parse JSON fields
    attributes = _parse_json_safe(span_data.attributes_json, {})
    events = _parse_json_safe(span_data.events_json, [])
    # resource_attributes is available but not used in current API response
    _ = _parse_json_safe(span_data.resource_attributes_json, {})

    # Extract junjo fields from attributes
    junjo_id = attributes.pop("junjo.id", "")
    junjo_parent_id = attributes.pop("junjo.parent_id", "")
    junjo_span_type = attributes.pop("junjo.span_type", "")
    junjo_wf_state_start = attributes.pop("junjo.wf_state_start", {})
    junjo_wf_state_end = attributes.pop("junjo.wf_state_end", {})
    junjo_wf_graph_structure = attributes.pop("junjo.wf_graph_structure", {})
    junjo_wf_store_id = attributes.pop("junjo.wf_store_id", "")

    # Parse nested JSON in junjo fields if they're strings
    if isinstance(junjo_wf_state_start, str):
        junjo_wf_state_start = _parse_json_safe(junjo_wf_state_start, {})
    if isinstance(junjo_wf_state_end, str):
        junjo_wf_state_end = _parse_json_safe(junjo_wf_state_end, {})
    if isinstance(junjo_wf_graph_structure, str):
        junjo_wf_graph_structure = _parse_json_safe(junjo_wf_graph_structure, {})

    # Map span_kind int to string (matching V3 behavior)
    kind_map = {0: "INTERNAL", 1: "SERVER", 2: "CLIENT", 3: "PRODUCER", 4: "CONSUMER"}
    kind_str = kind_map.get(span_data.span_kind, "INTERNAL")

    # Format timestamps
    start_time_str = _format_timestamp_ns(span_data.start_time_unix_nano)
    end_time_str = _format_timestamp_ns(span_data.end_time_unix_nano)

    return {
        "trace_id": span_data.trace_id,
        "span_id": span_data.span_id,
        "parent_span_id": span_data.parent_span_id,
        "service_name": span_data.service_name,
        "name": span_data.name,
        "kind": kind_str,
        "start_time": start_time_str,
        "end_time": end_time_str,
        "status_code": str(span_data.status_code),
        "status_message": span_data.status_message or "",
        "attributes_json": attributes,
        "events_json": events,
        "links_json": [],  # Not in WAL schema
        "trace_flags": 0,  # Not in WAL schema
        "trace_state": None,  # Not in WAL schema
        "junjo_id": junjo_id,
        "junjo_parent_id": junjo_parent_id,
        "junjo_span_type": junjo_span_type,
        "junjo_wf_state_start": junjo_wf_state_start,
        "junjo_wf_state_end": junjo_wf_state_end,
        "junjo_wf_graph_structure": junjo_wf_graph_structure,
        "junjo_wf_store_id": junjo_wf_store_id,
    }


def _parse_json_safe(value: str | None, default: Any) -> Any:
    """Parse JSON string safely, returning default on failure."""
    if value is None or value == "":
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _format_timestamp_ns(ts_ns: int) -> str:
    """Format nanosecond timestamp to ISO8601 string with timezone."""
    if ts_ns == 0:
        return ""
    seconds = ts_ns // 1_000_000_000
    remaining_ns = ts_ns % 1_000_000_000
    microseconds = remaining_ns // 1000
    dt = datetime.fromtimestamp(seconds, tz=UTC)
    dt = dt.replace(microsecond=microseconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "+00:00"
