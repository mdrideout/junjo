//! OTLP export requests: built from a shared telemetry fixture, or span by
//! span for a test that needs one particular trace.

use chrono::DateTime;
use junjo_evidence::json::Json;
use opentelemetry_proto::tonic::collector::trace::v1::ExportTraceServiceRequest;
use opentelemetry_proto::tonic::common::v1::any_value::Value;
use opentelemetry_proto::tonic::common::v1::{AnyValue, ArrayValue, KeyValue, KeyValueList};
use opentelemetry_proto::tonic::resource::v1::Resource;
use opentelemetry_proto::tonic::trace::v1::span::{Event, Link, SpanKind};
use opentelemetry_proto::tonic::trace::v1::{ResourceSpans, ScopeSpans, Span, Status};

/// When a span built by `span` starts: 2025-01-15T10:30:00Z.
pub const START_NS: u64 = 1_736_937_000_000_000_000;

/// The bytes of a hexadecimal trace or span identifier.
pub fn hex_bytes(hex: &str) -> Vec<u8> {
    (0..hex.len())
        .step_by(2)
        .map(|index| u8::from_str_radix(&hex[index..index + 2], 16).expect("hexadecimal"))
        .collect()
}

/// An attribute whose value is text.
pub fn text_attribute(key: &str, value: &str) -> KeyValue {
    KeyValue {
        key: key.to_string(),
        value: Some(AnyValue {
            value: Some(Value::StringValue(value.to_string())),
        }),
    }
}

/// An internal root span that lasts one millisecond. A test changes the
/// fields it cares about with struct update syntax.
pub fn span(trace_id: &str, span_id: &str, name: &str) -> Span {
    Span {
        trace_id: hex_bytes(trace_id),
        span_id: hex_bytes(span_id),
        name: name.to_string(),
        kind: SpanKind::Internal as i32,
        start_time_unix_nano: START_NS,
        end_time_unix_nano: START_NS + 1_000_000,
        ..Default::default()
    }
}

/// One export of spans that one service emitted.
pub fn export_request(service_name: &str, spans: Vec<Span>) -> ExportTraceServiceRequest {
    ExportTraceServiceRequest {
        resource_spans: vec![ResourceSpans {
            resource: Some(Resource {
                attributes: vec![text_attribute("service.name", service_name)],
                ..Default::default()
            }),
            scope_spans: vec![ScopeSpans {
                spans,
                ..Default::default()
            }],
            ..Default::default()
        }],
    }
}

/// One export of every span of a shared telemetry fixture. A fixture gives
/// its spans in the raw span API's shape. Each span is sent under its own
/// resource, because each carries its own resource attributes.
pub fn fixture_export_request(case: &Json) -> ExportTraceServiceRequest {
    let resource_spans = array(case, "spans")
        .iter()
        .map(|span| ResourceSpans {
            resource: Some(Resource {
                attributes: key_values(&span["resource_attributes_json"]),
                dropped_attributes_count: count(span, "resource_dropped_attributes_count"),
                ..Default::default()
            }),
            scope_spans: vec![ScopeSpans {
                spans: vec![fixture_span(span)],
                ..Default::default()
            }],
            ..Default::default()
        })
        .collect();
    ExportTraceServiceRequest { resource_spans }
}

fn fixture_span(span: &Json) -> Span {
    let kind = match text(span, "kind") {
        "UNSPECIFIED" => SpanKind::Unspecified,
        "INTERNAL" => SpanKind::Internal,
        "SERVER" => SpanKind::Server,
        "CLIENT" => SpanKind::Client,
        "PRODUCER" => SpanKind::Producer,
        "CONSUMER" => SpanKind::Consumer,
        other => panic!("unknown span kind {other}"),
    };
    Span {
        trace_id: hex_bytes(text(span, "trace_id")),
        span_id: hex_bytes(text(span, "span_id")),
        // A root span has a null parent and a span without trace state has a
        // null trace state. OTLP sends both as empty.
        parent_span_id: span["parent_span_id"]
            .as_str()
            .map(hex_bytes)
            .unwrap_or_default(),
        trace_state: span["trace_state"].as_str().unwrap_or_default().to_string(),
        flags: count(span, "trace_flags"),
        name: text(span, "name").to_string(),
        kind: kind as i32,
        start_time_unix_nano: nanoseconds(span, "start_time"),
        end_time_unix_nano: nanoseconds(span, "end_time"),
        attributes: key_values(&span["attributes_json"]),
        dropped_attributes_count: count(span, "dropped_attributes_count"),
        events: array(span, "events_json")
            .iter()
            .map(fixture_event)
            .collect(),
        dropped_events_count: count(span, "dropped_events_count"),
        links: array(span, "links_json").iter().map(fixture_link).collect(),
        dropped_links_count: count(span, "dropped_links_count"),
        status: Some(Status {
            code: text(span, "status_code").parse().expect("status_code"),
            message: text(span, "status_message").to_string(),
        }),
    }
}

fn fixture_event(event: &Json) -> Event {
    Event {
        // The events contract stores nanoseconds as text.
        time_unix_nano: text(event, "timeUnixNano").parse().expect("timeUnixNano"),
        name: text(event, "name").to_string(),
        attributes: key_values(&event["attributes"]),
        dropped_attributes_count: count(event, "droppedAttributesCount"),
    }
}

/// A link names its trace and span. Its other members are optional.
fn fixture_link(link: &Json) -> Link {
    let optional_count = |name: &str| match link.get(name) {
        Some(_) => count(link, name),
        None => 0,
    };
    Link {
        trace_id: hex_bytes(text(link, "traceId")),
        span_id: hex_bytes(text(link, "spanId")),
        trace_state: link["traceState"].as_str().unwrap_or_default().to_string(),
        attributes: link.get("attributes").map(key_values).unwrap_or_default(),
        dropped_attributes_count: optional_count("droppedAttributesCount"),
        flags: optional_count("flags"),
    }
}

/// The members of a JSON object as OTLP attributes, in the object's order.
fn key_values(object: &Json) -> Vec<KeyValue> {
    object
        .as_object()
        .expect("an object of attributes")
        .iter()
        .map(|(key, value)| KeyValue {
            key: key.clone(),
            value: Some(any_value(value)),
        })
        .collect()
}

fn any_value(value: &Json) -> AnyValue {
    let value = match value {
        Json::Null => None,
        Json::Bool(flag) => Some(Value::BoolValue(*flag)),
        Json::Number(number) => Some(match number.as_i64() {
            Some(integer) => Value::IntValue(integer),
            None => Value::DoubleValue(number.as_f64().expect("a JSON number")),
        }),
        Json::String(text) => Some(Value::StringValue(text.clone())),
        Json::Array(items) => Some(Value::ArrayValue(ArrayValue {
            values: items.iter().map(any_value).collect(),
        })),
        Json::Object(_) => Some(Value::KvlistValue(KeyValueList {
            values: key_values(value),
        })),
    };
    AnyValue { value }
}

fn text<'a>(value: &'a Json, name: &str) -> &'a str {
    value[name].as_str().expect(name)
}

fn array<'a>(value: &'a Json, name: &str) -> &'a [Json] {
    value[name].as_array().expect(name)
}

fn count(value: &Json, name: &str) -> u32 {
    u32::try_from(value[name].as_u64().expect(name)).expect(name)
}

/// An RFC 3339 timestamp as nanoseconds since the Unix epoch.
fn nanoseconds(value: &Json, name: &str) -> u64 {
    let timestamp = DateTime::parse_from_rfc3339(text(value, name)).expect(name);
    u64::try_from(timestamp.timestamp_nanos_opt().expect(name)).expect(name)
}
