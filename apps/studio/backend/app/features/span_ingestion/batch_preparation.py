"""Batch preparation utilities for span ingestion.

This module handles the unmarshaling of OTLP spans and extraction of per-span
service names from resource attributes. Extracted to keep background_poller.py
focused on orchestration logic.
"""

from loguru import logger
from opentelemetry.proto.resource.v1 import resource_pb2
from opentelemetry.proto.trace.v1 import trace_pb2


def unmarshal_spans_with_service_names(
    spans_with_resources: list,
) -> list[tuple[trace_pb2.Span, str]]:
    """Unmarshal OTLP spans and extract service name for each span.

    This function processes raw span+resource pairs from the ingestion service:
    1. Unmarshals each span's protobuf bytes
    2. Extracts service.name from each span's resource attributes
    3. Returns list of (span, service_name) tuples

    Args:
        spans_with_resources: List of objects with attributes:
            - span_bytes: Serialized OTLP Span protobuf
            - resource_bytes: Serialized OTLP Resource protobuf
            - key_ulid: ULID key for logging

    Returns:
        List of (span, service_name) tuples for successfully processed spans.
        Spans that fail to unmarshal or have no service name are logged and skipped.

    Example:
        >>> spans_with_resources = await client.read_spans(last_key, batch_size=100)
        >>> spans_with_service_names = unmarshal_spans_with_service_names(spans_with_resources)
        >>> for span, service_name in spans_with_service_names:
        ...     process_span(span, service_name)

    Error Handling:
        - Unmarshal errors: Log warning, skip span, continue with batch
        - Missing service.name: Use "NO_SERVICE_NAME", log warning
        - Resource parse errors: Use "NO_SERVICE_NAME", log warning
    """
    result = []

    for span_with_resource in spans_with_resources:
        # 1. Unmarshal span protobuf
        try:
            span = trace_pb2.Span()
            span.ParseFromString(span_with_resource.span_bytes)
        except Exception as e:
            logger.warning(
                "Error unmarshaling span",
                extra={
                    "key_ulid": span_with_resource.key_ulid.hex(),
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            continue  # Skip corrupted span

        # 2. Extract service_name from this span's resource
        service_name = "NO_SERVICE_NAME"
        try:
            resource = resource_pb2.Resource()
            resource.ParseFromString(span_with_resource.resource_bytes)

            # Search for service.name attribute
            for attr in resource.attributes:
                if attr.key == "service.name" and attr.value.HasField("string_value"):
                    service_name = attr.value.string_value
                    break

            if service_name == "NO_SERVICE_NAME":
                logger.warning(
                    "No service.name attribute found in resource, using default",
                    extra={"key_ulid": span_with_resource.key_ulid.hex()},
                )

        except Exception as e:
            logger.warning(
                "Error extracting service name from resource, using default",
                extra={
                    "key_ulid": span_with_resource.key_ulid.hex(),
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

        # 3. Add to results
        result.append((span, service_name))

    return result
