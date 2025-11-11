"""OTLP span processor for DuckDB indexing.

This module processes OpenTelemetry Protocol (OTLP) spans from the ingestion
service and indexes them in DuckDB. It handles:
- All 6 OTLP attribute types (string, int, double, bool, array, kvlist, bytes)
- Junjo custom attributes extraction
- State patch extraction from span events
- Timestamp conversion (nanosecond → microsecond)

Port of: backend/telemetry/otel_span_processor.go
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.trace.v1 import trace_pb2

from app.db_duckdb.db_config import get_connection

# Junjo attributes stored in dedicated columns (filtered from attributes_json)
JUNJO_FILTERED_ATTRIBUTES = [
    "junjo.workflow_id",  # Legacy (not extracted, kept for compatibility)
    "node.id",  # Legacy (not extracted, kept for compatibility)
    "junjo.id",
    "junjo.parent_id",
    "junjo.span_type",
    "junjo.workflow.state.start",
    "junjo.workflow.state.end",
    "junjo.workflow.graph_structure",
    "junjo.workflow.store.id",
]


def convert_kind(kind: int) -> str:
    """Convert OTLP span kind integer to string representation.

    Args:
        kind: OTLP SpanKind enum value (0-5)

    Returns:
        String representation: "UNSPECIFIED", "INTERNAL", "SERVER", "CLIENT",
        "PRODUCER", "CONSUMER"

    Reference: otel_span_processor.go:19-35
    """
    kind_map = {
        0: "UNSPECIFIED",
        1: "CLIENT",
        2: "SERVER",
        3: "INTERNAL",
        4: "PRODUCER",
        5: "CONSUMER",
    }
    return kind_map.get(kind, "UNSPECIFIED")


def convert_otlp_timestamp(ts_nano: int) -> datetime:
    """Convert OTLP uint64 nanoseconds to timezone-aware datetime.

    Args:
        ts_nano: Nanoseconds since Unix epoch (from OTLP protobuf)

    Returns:
        Timezone-aware datetime with microsecond precision (UTC)

    Precision Loss:
        Input nanoseconds are truncated to microseconds (3 decimal places lost).
        This is inherent to both Python datetime and DuckDB TIMESTAMPTZ.

    Example:
        >>> ts_nano = 1699876543123456789
        >>> dt = convert_otlp_timestamp(ts_nano)
        >>> print(dt)
        2023-11-13 12:15:43.123456+00:00

    Reference: otel_span_processor.go:163-164
    """
    return datetime.fromtimestamp(ts_nano / 1e9, tz=UTC)


def extract_string_attribute(attributes: list[common_pb2.KeyValue], key: str) -> str:
    """Extract string attribute value by key.

    Args:
        attributes: List of OTLP KeyValue attributes
        key: Attribute key to search for

    Returns:
        String value if found and is string type, empty string otherwise

    Reference: otel_span_processor.go:37-47
    """
    for attr in attributes:
        if attr.key == key and attr.value.HasField("string_value"):
            return attr.value.string_value
    return ""


def extract_json_attribute(attributes: list[common_pb2.KeyValue], key: str) -> str:
    """Extract JSON string attribute value by key.

    Args:
        attributes: List of OTLP KeyValue attributes
        key: Attribute key to search for

    Returns:
        JSON string value if found, "{}" (empty JSON object) otherwise

    Reference: otel_span_processor.go:49-59
    """
    for attr in attributes:
        if attr.key == key and attr.value.HasField("string_value"):
            return attr.value.string_value
    return "{}"  # Default to empty JSON object


def convert_otlp_value(value: common_pb2.AnyValue) -> Any:
    """Convert OTLP AnyValue to Python type using pattern matching.

    This handles all 6 OTLP attribute types:
    - StringValue → str
    - IntValue → int
    - DoubleValue → float
    - BoolValue → bool
    - ArrayValue → list (recursive)
    - KvlistValue → dict (recursive)
    - BytesValue → str (hex-encoded)

    Args:
        value: OTLP AnyValue protobuf

    Returns:
        Python native type, or None if unsupported

    Limitations:
        - Arrays only support primitive elements (no nested arrays/objects)
        - Kvlists only support primitive values (no nested objects)

    Reference: otel_span_processor.go:62-120
    """
    match value.WhichOneof("value"):
        case "string_value":
            return value.string_value

        case "int_value":
            return value.int_value

        case "double_value":
            return value.double_value

        case "bool_value":
            return value.bool_value

        case "array_value":
            arr = []
            for item in value.array_value.values:
                # Only support primitive types in arrays
                if item.HasField("string_value"):
                    arr.append(item.string_value)
                elif item.HasField("int_value"):
                    arr.append(item.int_value)
                elif item.HasField("double_value"):
                    arr.append(item.double_value)
                elif item.HasField("bool_value"):
                    arr.append(item.bool_value)
                else:
                    logger.warning(f"Unsupported array element type: {item.WhichOneof('value')}")
            return arr

        case "kvlist_value":
            kvlist_map = {}
            for kv in value.kvlist_value.values:
                # Only support primitive values in kvlists
                kv_value = kv.value
                if kv_value.HasField("string_value"):
                    kvlist_map[kv.key] = kv_value.string_value
                elif kv_value.HasField("int_value"):
                    kvlist_map[kv.key] = kv_value.int_value
                elif kv_value.HasField("double_value"):
                    kvlist_map[kv.key] = kv_value.double_value
                elif kv_value.HasField("bool_value"):
                    kvlist_map[kv.key] = kv_value.bool_value
                else:
                    logger.warning(
                        f"Unsupported kvlist element type: {kv_value.WhichOneof('value')}"
                    )
            return kvlist_map

        case "bytes_value":
            return value.bytes_value.hex()

        case _:
            logger.warning(f"Unsupported OTLP type: {value.WhichOneof('value')}")
            return None


def convert_attributes_to_json(attributes: list[common_pb2.KeyValue]) -> str:
    """Convert OTLP KeyValue attributes to JSON string.

    Args:
        attributes: List of OTLP KeyValue attributes

    Returns:
        JSON string representation of attributes

    Raises:
        ValueError: If JSON marshaling fails

    Reference: otel_span_processor.go:61-120
    """
    attr_map = {}
    for attr in attributes:
        converted_value = convert_otlp_value(attr.value)
        if converted_value is not None:
            attr_map[attr.key] = converted_value

    try:
        return json.dumps(attr_map)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Failed to marshal attributes to JSON: {e}")


def convert_events_to_json(events: list[trace_pb2.Span.Event]) -> str:
    """Convert OTLP span events to JSON string.

    Args:
        events: List of OTLP span events

    Returns:
        JSON array string with event objects

    Raises:
        ValueError: If JSON marshaling fails

    Reference: otel_span_processor.go:122-145
    """
    event_list = []
    for event in events:
        attributes_json = convert_attributes_to_json(event.attributes)

        event_map = {
            "name": event.name,
            "timeUnixNano": event.time_unix_nano,
            "droppedAttributesCount": event.dropped_attributes_count,
            "attributes": json.loads(attributes_json),  # Nested JSON object
        }
        event_list.append(event_map)

    try:
        return json.dumps(event_list)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Failed to marshal events to JSON: {e}")


def filter_junjo_attributes(
    attributes: list[common_pb2.KeyValue],
) -> list[common_pb2.KeyValue]:
    """Filter out Junjo attributes that are stored in dedicated columns.

    Args:
        attributes: List of OTLP KeyValue attributes

    Returns:
        Filtered list with Junjo dedicated-column attributes removed

    Reference: otel_span_processor.go:202-211
    """
    return [attr for attr in attributes if attr.key not in JUNJO_FILTERED_ATTRIBUTES]


def process_single_span(conn, service_name: str, span: trace_pb2.Span) -> tuple[str, str, str, str]:
    """Process a single OTLP span and insert into DuckDB.

    This function:
    1. Encodes trace/span IDs to hex
    2. Converts timestamps from nanoseconds to datetime
    3. Extracts Junjo custom attributes to dedicated columns
    4. Filters Junjo attributes from attributes_json
    5. Converts attributes and events to JSON
    6. Inserts span into DuckDB
    7. Returns identifiers for state patch processing

    Args:
        conn: DuckDB connection (within transaction)
        service_name: Service name from resource
        span: OTLP Span protobuf

    Returns:
        Tuple of (trace_id, span_id, workflow_id, node_id) for state patches

    Raises:
        ValueError: If data validation fails
        Exception: If database insert fails

    Reference: otel_span_processor.go:147-278
    """
    # 1. Encode IDs
    trace_id = span.trace_id.hex()
    span_id = span.span_id.hex()
    parent_span_id = span.parent_span_id.hex() if span.parent_span_id else None

    # 2. Timestamps
    start_time = convert_otlp_timestamp(span.start_time_unix_nano)
    end_time = convert_otlp_timestamp(span.end_time_unix_nano)

    # 3. Standard Attributes
    kind_str = convert_kind(span.kind)
    status_code = ""
    status_message = ""
    if span.status:
        status_code = str(span.status.code)
        status_message = span.status.message

    # 4. Junjo Attributes - Span Identification
    junjo_span_type = extract_string_attribute(span.attributes, "junjo.span_type")
    junjo_parent_id = extract_string_attribute(span.attributes, "junjo.parent_id")
    junjo_id = extract_string_attribute(span.attributes, "junjo.id")

    # Extract workflow_id and node_id based on span type
    workflow_id = ""
    if junjo_span_type == "workflow":
        workflow_id = junjo_id

    node_id = ""
    if junjo_span_type == "node":
        node_id = junjo_id

    # 5. Workflow State Attributes (only for workflow/subflow spans)
    junjo_initial_state = "{}"
    junjo_final_state = "{}"
    junjo_graph_structure = "{}"
    junjo_wf_store_id = ""
    if junjo_span_type in ("workflow", "subflow"):
        junjo_initial_state = extract_json_attribute(span.attributes, "junjo.workflow.state.start")
        junjo_final_state = extract_json_attribute(span.attributes, "junjo.workflow.state.end")
        junjo_graph_structure = extract_json_attribute(
            span.attributes, "junjo.workflow.graph_structure"
        )
        # Fix: Use extract_string_attribute for store.id (it's a string, not JSON)
        junjo_wf_store_id = extract_string_attribute(span.attributes, "junjo.workflow.store.id")

    # 6. Filter and Convert Attributes
    filtered_attributes = filter_junjo_attributes(span.attributes)
    attributes_json = convert_attributes_to_json(filtered_attributes)
    events_json = convert_events_to_json(span.events)

    # 7. Handle Optional Fields
    trace_state = span.trace_state if span.trace_state else None

    # 8. Insert Span
    span_insert_query = """
        INSERT OR IGNORE INTO spans (
            trace_id, span_id, parent_span_id, service_name, name, kind,
            start_time, end_time, status_code, status_message,
            attributes_json, events_json, links_json,
            trace_flags, trace_state,
            junjo_id, junjo_parent_id, junjo_span_type,
            junjo_wf_state_start, junjo_wf_state_end,
            junjo_wf_graph_structure, junjo_wf_store_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    conn.execute(
        span_insert_query,
        (
            trace_id,
            span_id,
            parent_span_id,
            service_name,
            span.name,
            kind_str,
            start_time,
            end_time,
            status_code,
            status_message,
            attributes_json,
            events_json,
            "[]",  # links_json - empty for now
            span.flags,
            trace_state,
            junjo_id,
            junjo_parent_id,
            junjo_span_type,
            junjo_initial_state,
            junjo_final_state,
            junjo_graph_structure,
            junjo_wf_store_id,
        ),
    )

    return trace_id, span_id, workflow_id, node_id


def process_state_patches(
    conn,
    events: list[trace_pb2.Span.Event],
    trace_id: str,
    span_id: str,
    workflow_id: str,
    node_id: str,
    service_name: str,
) -> None:
    """Extract and insert state patches from span events.

    Searches for events named "set_state" and extracts state patches from them.
    Each patch is inserted into the state_patches table.

    Args:
        conn: DuckDB connection (within transaction)
        events: Span events
        trace_id, span_id: Parent span identifiers
        workflow_id, node_id: From span attributes
        service_name: Service name

    Reference: otel_span_processor.go:257-275
    """
    patch_insert_query = """
        INSERT OR IGNORE INTO state_patches (
            patch_id, service_name, trace_id, span_id,
            workflow_id, node_id, event_time,
            patch_json, patch_store_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    for event in events:
        if event.name == "set_state":
            try:
                event_time = convert_otlp_timestamp(event.time_unix_nano)
                patch_json = extract_json_attribute(event.attributes, "junjo.state_json_patch")
                patch_store_id = extract_string_attribute(event.attributes, "junjo.store.id")
                patch_id = str(uuid.uuid4())

                conn.execute(
                    patch_insert_query,
                    (
                        patch_id,
                        service_name,
                        trace_id,
                        span_id,
                        workflow_id,
                        node_id,
                        event_time,
                        patch_json,
                        patch_store_id,
                    ),
                )
            except Exception as e:
                logger.error(
                    "Failed to insert state patch",
                    extra={
                        "trace_id": trace_id,
                        "span_id": span_id,
                        "event_time": event.time_unix_nano,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                # Note: Go implementation logs but continues
                # Python: match Go behavior (don't raise)


def process_span_batch(service_name: str, spans: list[trace_pb2.Span]) -> None:
    """Process batch of OTLP spans in a single transaction.

    This is the main entry point for span processing. It:
    1. Opens a DuckDB connection with context manager
    2. Begins a transaction
    3. Processes each span (insert span + extract state patches)
    4. Commits transaction on success, rollback on error

    Args:
        service_name: Service name from resource
        spans: List of OTLP Span protobufs

    Raises:
        Exception: If any span processing fails (entire batch rolls back)

    Reference: otel_span_processor.go:280-305
    """
    if not spans:
        return

    with get_connection() as conn:
        try:
            conn.execute("BEGIN TRANSACTION")

            for span in spans:
                # Process span and get identifiers for state patches
                trace_id, span_id, workflow_id, node_id = process_single_span(
                    conn, service_name, span
                )

                # Extract and insert state patches
                process_state_patches(
                    conn, span.events, trace_id, span_id, workflow_id, node_id, service_name
                )

            conn.execute("COMMIT")
            logger.info(f"Successfully processed batch of {len(spans)} spans")

        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(
                "Failed to process span batch",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "batch_size": len(spans),
                    "service_name": service_name,
                },
            )
            raise
