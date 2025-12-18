use std::sync::Arc;
use arrow::datatypes::{DataType, Field, Schema, TimeUnit};

lazy_static::lazy_static! {
    /// Arrow schema for span records, matching the Go implementation for DataFusion compatibility.
    pub static ref SPAN_SCHEMA: Arc<Schema> = Arc::new(Schema::new(vec![
        Field::new("span_id", DataType::Utf8, false),
        Field::new("trace_id", DataType::Utf8, false),
        Field::new("parent_span_id", DataType::Utf8, true),
        Field::new("service_name", DataType::Utf8, false),
        Field::new("name", DataType::Utf8, false),
        Field::new("span_kind", DataType::Int8, false),
        Field::new("start_time", DataType::Timestamp(TimeUnit::Nanosecond, Some("UTC".into())), false),
        Field::new("end_time", DataType::Timestamp(TimeUnit::Nanosecond, Some("UTC".into())), false),
        Field::new("duration_ns", DataType::Int64, false),
        Field::new("status_code", DataType::Int8, false),
        Field::new("status_message", DataType::Utf8, true),
        Field::new("attributes", DataType::Utf8, false),
        Field::new("events", DataType::Utf8, false),
        Field::new("resource_attributes", DataType::Utf8, false),
    ]));
}
