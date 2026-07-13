use opentelemetry_proto::tonic::common::v1::{any_value, AnyValue, KeyValue};
use opentelemetry_proto::tonic::resource::v1::Resource;
use opentelemetry_proto::tonic::trace::v1::Span;
use serde_json::{json, Value as JsonValue};

/// A span record in a format suitable for Arrow/Parquet storage.
#[derive(Debug, Clone)]
pub struct SpanRecord {
    pub span_id: String,
    pub trace_id: String,
    pub parent_span_id: Option<String>,
    pub service_name: String,
    pub name: String,
    pub span_kind: i8,
    pub start_time_ns: i64,
    pub end_time_ns: i64,
    pub duration_ns: i64,
    pub status_code: i8,
    pub status_message: Option<String>,
    pub attributes: String,
    pub events: String,
    pub resource_attributes: String,
}

impl SpanRecord {
    /// Convert an OTLP span and resource to a SpanRecord.
    pub fn from_otlp(span: &Span, resource: Option<&Resource>) -> Self {
        let span_id = hex::encode(&span.span_id);
        let trace_id = hex::encode(&span.trace_id);
        let parent_span_id = if span.parent_span_id.is_empty() {
            None
        } else {
            Some(hex::encode(&span.parent_span_id))
        };

        let service_name = resource
            .and_then(|r| r.attributes.iter().find(|kv| kv.key == "service.name"))
            .and_then(|kv| kv.value.as_ref())
            .and_then(extract_string_value)
            .unwrap_or_default();

        let span_kind = span.kind as i8;
        let start_time_ns = span.start_time_unix_nano as i64;
        let end_time_ns = span.end_time_unix_nano as i64;
        let duration_ns = end_time_ns - start_time_ns;

        let (status_code, status_message) = span
            .status
            .as_ref()
            .map(|s| {
                (
                    s.code as i8,
                    if s.message.is_empty() {
                        None
                    } else {
                        Some(s.message.clone())
                    },
                )
            })
            .unwrap_or((0, None));

        let attributes = serialize_attributes(&span.attributes);
        let events = serialize_events(&span.events);
        let resource_attributes = resource
            .map(|r| serialize_attributes(&r.attributes))
            .unwrap_or_else(|| "{}".to_string());

        SpanRecord {
            span_id,
            trace_id,
            parent_span_id,
            service_name,
            name: span.name.clone(),
            span_kind,
            start_time_ns,
            end_time_ns,
            duration_ns,
            status_code,
            status_message,
            attributes,
            events,
            resource_attributes,
        }
    }
}

fn extract_string_value(value: &AnyValue) -> Option<String> {
    match &value.value {
        Some(any_value::Value::StringValue(s)) => Some(s.clone()),
        _ => None,
    }
}

fn serialize_attributes(attrs: &[KeyValue]) -> String {
    let map: serde_json::Map<String, JsonValue> = attrs
        .iter()
        .filter_map(|kv| {
            kv.value
                .as_ref()
                .map(|v| (kv.key.clone(), any_value_to_json(v)))
        })
        .collect();

    serde_json::to_string(&map).unwrap_or_else(|_| "{}".to_string())
}

fn serialize_events(events: &[opentelemetry_proto::tonic::trace::v1::span::Event]) -> String {
    let event_list: Vec<JsonValue> = events
        .iter()
        .map(|e| {
            let attrs: serde_json::Map<String, JsonValue> = e
                .attributes
                .iter()
                .filter_map(|kv| {
                    kv.value
                        .as_ref()
                        .map(|v| (kv.key.clone(), any_value_to_json(v)))
                })
                .collect();

            json!({
                "name": e.name,
                "timeUnixNano": e.time_unix_nano,
                "attributes": attrs,
            })
        })
        .collect();

    serde_json::to_string(&event_list).unwrap_or_else(|_| "[]".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use opentelemetry_proto::tonic::common::v1::{any_value, AnyValue, KeyValue};
    use opentelemetry_proto::tonic::resource::v1::Resource;
    use opentelemetry_proto::tonic::trace::v1::span::Event;
    use opentelemetry_proto::tonic::trace::v1::{Span, Status};

    fn string_value(value: &str) -> AnyValue {
        AnyValue {
            value: Some(any_value::Value::StringValue(value.to_string())),
        }
    }

    fn bool_value(value: bool) -> AnyValue {
        AnyValue {
            value: Some(any_value::Value::BoolValue(value)),
        }
    }

    fn key_value(key: &str, value: AnyValue) -> KeyValue {
        KeyValue {
            key: key.to_string(),
            value: Some(value),
        }
    }

    #[test]
    fn test_serialize_events_uses_time_unix_nano_camel_case() {
        let event = Event {
            time_unix_nano: 123,
            name: "set_state".to_string(),
            attributes: vec![],
            dropped_attributes_count: 0,
        };

        let json_str = serialize_events(&[event]);
        let parsed: serde_json::Value = serde_json::from_str(&json_str).unwrap();

        let event_obj = parsed
            .as_array()
            .unwrap()
            .first()
            .unwrap()
            .as_object()
            .unwrap();
        assert!(event_obj.contains_key("timeUnixNano"));
        assert!(!event_obj.contains_key("time_unix_nano"));
    }

    #[test]
    fn test_from_otlp_preserves_current_junjo_attributes_and_resource_service_name() {
        let span = Span {
            trace_id: vec![0x11; 16],
            span_id: vec![0x22; 8],
            parent_span_id: vec![],
            name: "workflow".to_string(),
            kind: 0,
            start_time_unix_nano: 100,
            end_time_unix_nano: 200,
            attributes: vec![
                key_value(
                    "junjo.workflow.execution_graph_snapshot",
                    string_value("{\"v\":2,\"graphStructuralId\":\"graph-basic-01\"}"),
                ),
                key_value(
                    "junjo.executable_runtime_id",
                    string_value("run-basic-01"),
                ),
                key_value(
                    "junjo.executable_structural_id",
                    string_value("graph-basic-01"),
                ),
                key_value("error.type", string_value("ValueError")),
                key_value("junjo.cancelled", bool_value(true)),
            ],
            events: vec![],
            links: vec![],
            status: Some(Status {
                code: 2,
                message: "failed".to_string(),
            }),
            ..Default::default()
        };
        let resource = Resource {
            attributes: vec![key_value("service.name", string_value("svc-phase0"))],
            dropped_attributes_count: 0,
            entity_refs: vec![],
        };

        let record = SpanRecord::from_otlp(&span, Some(&resource));
        let attributes: serde_json::Value = serde_json::from_str(&record.attributes).unwrap();
        let resource_attributes: serde_json::Value =
            serde_json::from_str(&record.resource_attributes).unwrap();

        assert_eq!(record.service_name, "svc-phase0");
        assert_eq!(
            attributes["junjo.workflow.execution_graph_snapshot"],
            "{\"v\":2,\"graphStructuralId\":\"graph-basic-01\"}"
        );
        assert_eq!(attributes["junjo.executable_runtime_id"], "run-basic-01");
        assert_eq!(attributes["junjo.executable_structural_id"], "graph-basic-01");
        assert_eq!(attributes["error.type"], "ValueError");
        assert_eq!(attributes["junjo.cancelled"], true);
        assert_eq!(resource_attributes["service.name"], "svc-phase0");
    }

    #[test]
    fn test_from_otlp_preserves_hook_error_and_set_state_events() {
        let span = Span {
            trace_id: vec![0x33; 16],
            span_id: vec![0x44; 8],
            parent_span_id: vec![],
            name: "node".to_string(),
            kind: 0,
            start_time_unix_nano: 300,
            end_time_unix_nano: 500,
            attributes: vec![],
            events: vec![
                Event {
                    time_unix_nano: 400,
                    name: "set_state".to_string(),
                    attributes: vec![
                        key_value("id", string_value("state-event-01")),
                        key_value("junjo.store.id", string_value("store-01")),
                        key_value("junjo.store.name", string_value("WorkflowState")),
                        key_value("junjo.store.action", string_value("set_value")),
                        key_value(
                            "junjo.state_json_patch",
                            string_value("[{\"op\":\"replace\",\"path\":\"/value\",\"value\":1}]"),
                        ),
                    ],
                    dropped_attributes_count: 0,
                },
                Event {
                    time_unix_nano: 450,
                    name: "junjo.hook_error".to_string(),
                    attributes: vec![
                        key_value(
                            "junjo.hook.event",
                            string_value("after_node_execution"),
                        ),
                        key_value(
                            "junjo.hook.callback",
                            string_value("tests.fixtures.HookFailureCallback"),
                        ),
                        key_value(
                            "junjo.hook.error.type",
                            string_value("RuntimeError"),
                        ),
                        key_value(
                            "junjo.hook.error.message",
                            string_value("hook exploded"),
                        ),
                        key_value("exception.type", string_value("RuntimeError")),
                        key_value("exception.message", string_value("hook exploded")),
                        key_value(
                            "exception.stacktrace",
                            string_value("Traceback (most recent call last)"),
                        ),
                    ],
                    dropped_attributes_count: 0,
                },
            ],
            links: vec![],
            status: Some(Status {
                code: 0,
                message: String::new(),
            }),
            ..Default::default()
        };

        let record = SpanRecord::from_otlp(&span, None);
        let events: serde_json::Value = serde_json::from_str(&record.events).unwrap();
        let event_list = events.as_array().unwrap();

        assert_eq!(event_list.len(), 2);
        assert_eq!(event_list[0]["name"], "set_state");
        assert_eq!(event_list[0]["timeUnixNano"], 400);
        assert_eq!(
            event_list[0]["attributes"]["junjo.store.id"],
            "store-01"
        );
        assert_eq!(event_list[1]["name"], "junjo.hook_error");
        assert_eq!(event_list[1]["timeUnixNano"], 450);
        assert_eq!(
            event_list[1]["attributes"]["junjo.hook.error.message"],
            "hook exploded"
        );
        assert_eq!(
            event_list[1]["attributes"]["exception.type"],
            "RuntimeError"
        );
    }
}

fn any_value_to_json(value: &AnyValue) -> JsonValue {
    match &value.value {
        Some(any_value::Value::StringValue(s)) => json!(s),
        Some(any_value::Value::IntValue(i)) => json!(i),
        Some(any_value::Value::DoubleValue(d)) => json!(d),
        Some(any_value::Value::BoolValue(b)) => json!(b),
        Some(any_value::Value::ArrayValue(arr)) => {
            let values: Vec<JsonValue> = arr.values.iter().map(any_value_to_json).collect();
            json!(values)
        }
        Some(any_value::Value::KvlistValue(kvlist)) => {
            let map: serde_json::Map<String, JsonValue> = kvlist
                .values
                .iter()
                .filter_map(|kv| {
                    kv.value
                        .as_ref()
                        .map(|v| (kv.key.clone(), any_value_to_json(v)))
                })
                .collect();
            json!(map)
        }
        Some(any_value::Value::BytesValue(b)) => json!(hex::encode(b)),
        None => JsonValue::Null,
    }
}
