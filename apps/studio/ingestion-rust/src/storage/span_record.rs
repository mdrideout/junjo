use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// SpanRecord represents a denormalized span ready for Arrow/Parquet storage.
/// This matches the schema used by the Go service and Python backend.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpanRecord {
    /// ULID key for ordering (8 bytes timestamp + 10 bytes random)
    pub ulid: String,

    /// OpenTelemetry trace ID (hex string, 32 chars)
    pub trace_id: String,

    /// OpenTelemetry span ID (hex string, 16 chars)
    pub span_id: String,

    /// Parent span ID (hex string, 16 chars, empty for root spans)
    pub parent_span_id: String,

    /// Span name/operation
    pub name: String,

    /// Service name from resource attributes
    pub service_name: String,

    /// Span kind (INTERNAL, SERVER, CLIENT, PRODUCER, CONSUMER)
    pub span_kind: String,

    /// Start time as RFC3339 timestamp
    pub start_time: DateTime<Utc>,

    /// End time as RFC3339 timestamp
    pub end_time: DateTime<Utc>,

    /// Duration in nanoseconds
    pub duration_ns: i64,

    /// Status code (OK, ERROR, UNSET)
    pub status_code: String,

    /// Status message (error description if status is ERROR)
    pub status_message: String,

    /// Span attributes as JSON object
    pub attributes_json: String,

    /// Resource attributes as JSON object
    pub resource_attributes_json: String,

    /// Span events as JSON array
    pub events_json: String,
}

impl SpanRecord {
    /// Check if this is a root span (no parent)
    pub fn is_root(&self) -> bool {
        self.parent_span_id.is_empty()
    }

    /// Check if this is a workflow span based on junjo.span_type attribute
    pub fn is_workflow(&self) -> bool {
        // Parse attributes to check span_type
        if let Ok(attrs) = serde_json::from_str::<serde_json::Value>(&self.attributes_json) {
            if let Some(span_type) = attrs.get("junjo.span_type") {
                return span_type.as_str() == Some("workflow");
            }
        }
        false
    }
}
