"""Helpers for converting shared Junjo fixtures into backend transport formats."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pyarrow as pa
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.resource.v1 import resource_pb2
from opentelemetry.proto.trace.v1 import trace_pb2

SPAN_SCHEMA = pa.schema(
    [
        pa.field("span_id", pa.string(), nullable=False),
        pa.field("trace_id", pa.string(), nullable=False),
        pa.field("parent_span_id", pa.string(), nullable=True),
        pa.field("service_name", pa.string(), nullable=False),
        pa.field("name", pa.string(), nullable=False),
        pa.field("span_kind", pa.int8(), nullable=False),
        pa.field("start_time", pa.timestamp("ns", tz="UTC"), nullable=False),
        pa.field("end_time", pa.timestamp("ns", tz="UTC"), nullable=False),
        pa.field("duration_ns", pa.int64(), nullable=False),
        pa.field("status_code", pa.int8(), nullable=False),
        pa.field("status_message", pa.string(), nullable=True),
        pa.field("attributes", pa.string(), nullable=False),
        pa.field("events", pa.string(), nullable=False),
        pa.field("links", pa.string(), nullable=False),
        pa.field("trace_flags", pa.uint32(), nullable=False),
        pa.field("trace_state", pa.string(), nullable=True),
        pa.field("dropped_attributes_count", pa.uint32(), nullable=False),
        pa.field("dropped_events_count", pa.uint32(), nullable=False),
        pa.field("dropped_links_count", pa.uint32(), nullable=False),
        pa.field("resource_attributes", pa.string(), nullable=False),
        pa.field("resource_dropped_attributes_count", pa.uint32(), nullable=False),
    ]
)

_KIND_TO_INT = {
    "INTERNAL": 0,
    "SERVER": 1,
    "CLIENT": 2,
    "PRODUCER": 3,
    "CONSUMER": 4,
}


def _iso_to_ns(value: str) -> int:
    dt = datetime.fromisoformat(value).astimezone(UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = dt - epoch
    return (
        ((delta.days * 24 * 60 * 60) + delta.seconds) * 1_000_000_000
        + delta.microseconds * 1_000
    )


def api_span_to_parquet_row(span: dict[str, Any]) -> dict[str, Any]:
    """Convert one backend-style API span fixture into a Parquet row."""
    start_ns = _iso_to_ns(span["start_time"])
    end_ns = _iso_to_ns(span["end_time"])
    return {
        "span_id": span["span_id"],
        "trace_id": span["trace_id"],
        "parent_span_id": span["parent_span_id"],
        "service_name": span["service_name"],
        "name": span["name"],
        "span_kind": _KIND_TO_INT[span["kind"]],
        "start_time": pa.scalar(start_ns, type=pa.timestamp("ns", tz="UTC")),
        "end_time": pa.scalar(end_ns, type=pa.timestamp("ns", tz="UTC")),
        "duration_ns": end_ns - start_ns,
        "status_code": int(span["status_code"]),
        "status_message": span["status_message"] or None,
        "attributes": json.dumps(span["attributes_json"], separators=(",", ":")),
        "events": json.dumps(span["events_json"], separators=(",", ":")),
        "links": json.dumps(span["links_json"], separators=(",", ":")),
        "trace_flags": span["trace_flags"],
        "trace_state": span["trace_state"],
        "dropped_attributes_count": span["dropped_attributes_count"],
        "dropped_events_count": span["dropped_events_count"],
        "dropped_links_count": span["dropped_links_count"],
        "resource_attributes": json.dumps(
            span["resource_attributes_json"],
            separators=(",", ":"),
        ),
        "resource_dropped_attributes_count": span["resource_dropped_attributes_count"],
    }


def _any_value(value: Any) -> common_pb2.AnyValue:
    if isinstance(value, bool):
        return common_pb2.AnyValue(bool_value=value)
    if isinstance(value, int):
        return common_pb2.AnyValue(int_value=value)
    if isinstance(value, float):
        return common_pb2.AnyValue(double_value=value)
    if isinstance(value, str):
        return common_pb2.AnyValue(string_value=value)
    if isinstance(value, list):
        return common_pb2.AnyValue(
            array_value=common_pb2.ArrayValue(values=[_any_value(item) for item in value])
        )
    if isinstance(value, dict):
        return common_pb2.AnyValue(
            kvlist_value=common_pb2.KeyValueList(
                values=[common_pb2.KeyValue(key=key, value=_any_value(item)) for key, item in value.items()]
            )
        )
    if value is None:
        return common_pb2.AnyValue()
    raise TypeError(f"Unsupported OTLP AnyValue type: {type(value).__name__}")


def _key_value(key: str, value: Any) -> common_pb2.KeyValue:
    return common_pb2.KeyValue(key=key, value=_any_value(value))


def _proto_event(event: dict[str, Any]) -> trace_pb2.Span.Event:
    return trace_pb2.Span.Event(
        time_unix_nano=int(event["timeUnixNano"]),
        name=event["name"],
        attributes=[_key_value(key, value) for key, value in event["attributes"].items()],
        dropped_attributes_count=event["droppedAttributesCount"],
    )


def _proto_link(link: dict[str, Any]) -> trace_pb2.Span.Link:
    return trace_pb2.Span.Link(
        trace_id=bytes.fromhex(link["traceId"]),
        span_id=bytes.fromhex(link["spanId"]),
        trace_state=link.get("traceState", ""),
        attributes=[_key_value(key, value) for key, value in link.get("attributes", {}).items()],
        dropped_attributes_count=link.get("droppedAttributesCount", 0),
        flags=link.get("flags", 0),
    )


def _proto_span(span: dict[str, Any]) -> trace_pb2.Span:
    return trace_pb2.Span(
        trace_id=bytes.fromhex(span["trace_id"]),
        span_id=bytes.fromhex(span["span_id"]),
        parent_span_id=(
            bytes.fromhex(span["parent_span_id"]) if span["parent_span_id"] else b""
        ),
        name=span["name"],
        kind=_KIND_TO_INT[span["kind"]],
        start_time_unix_nano=_iso_to_ns(span["start_time"]),
        end_time_unix_nano=_iso_to_ns(span["end_time"]),
        attributes=[
            _key_value(key, value) for key, value in span["attributes_json"].items()
        ],
        events=[_proto_event(event) for event in span["events_json"]],
        links=[_proto_link(link) for link in span["links_json"]],
        trace_state=span["trace_state"] or "",
        flags=span["trace_flags"],
        dropped_attributes_count=span["dropped_attributes_count"],
        dropped_events_count=span["dropped_events_count"],
        dropped_links_count=span["dropped_links_count"],
        status=trace_pb2.Status(
            code=int(span["status_code"]),
            message=span["status_message"],
        ),
    )


def build_otlp_export_request(case: dict[str, Any]) -> trace_service_pb2.ExportTraceServiceRequest:
    """Convert one shared fixture case into an OTLP ExportTraceServiceRequest."""
    resource_spans: list[trace_pb2.ResourceSpans] = []
    for span in case["spans"]:
        resource = resource_pb2.Resource(
            attributes=[
                _key_value(key, value) for key, value in span["resource_attributes_json"].items()
            ],
            dropped_attributes_count=span["resource_dropped_attributes_count"],
        )
        resource_spans.append(
            trace_pb2.ResourceSpans(
                resource=resource,
                scope_spans=[trace_pb2.ScopeSpans(spans=[_proto_span(span)])],
            )
        )

    return trace_service_pb2.ExportTraceServiceRequest(resource_spans=resource_spans)


def workflow_spans_for_case(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only workflow spans from a fixture case."""
    return [
        span
        for span in case["spans"]
        if span["attributes_json"].get("junjo.span_type") == "workflow"
    ]


def agent_spans_for_case(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only Agent executable owner spans from a fixture case."""
    return [
        span
        for span in case["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    ]


def _normalize_graph_snapshot(attributes: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(attributes)
    graph_snapshot = normalized.get("junjo.workflow.execution_graph_snapshot")
    if isinstance(graph_snapshot, str):
        normalized["junjo.workflow.execution_graph_snapshot"] = json.loads(graph_snapshot)
    return normalized


def normalize_api_span(span: dict[str, Any]) -> dict[str, Any]:
    """Normalize a backend API span for stable semantic comparisons."""
    normalized = deepcopy(span)
    normalized["attributes_json"] = _normalize_graph_snapshot(normalized["attributes_json"])
    normalized["events_json"] = sorted(
        normalized["events_json"],
        key=lambda event: (int(event["timeUnixNano"]), event["name"]),
    )
    return normalized


def normalize_api_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize and sort spans for semantic comparisons."""
    return sorted(
        (normalize_api_span(span) for span in spans),
        key=lambda span: (span["trace_id"], span["span_id"]),
    )
