use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};

use anyhow::{Context, Result};
use chrono::{DateTime, TimeZone, Utc};
use fjall::{Config as FjallConfig, Keyspace, PartitionHandle};
use prost::Message;
use tracing::{debug, info};
use ulid::Ulid;

use crate::config::StorageConfig;
use crate::proto::opentelemetry::proto::common::v1::AnyValue;
use crate::proto::opentelemetry::proto::resource::v1::Resource;
use crate::proto::opentelemetry::proto::trace::v1::span::SpanKind;
use crate::proto::opentelemetry::proto::trace::v1::status::StatusCode;
use crate::proto::opentelemetry::proto::trace::v1::Span;

use super::SpanRecord;

/// Key prefixes for different indexes in fjall.
/// Using single-byte prefixes for efficiency.
const PREFIX_SPAN: u8 = b's';        // Primary span data: s{ulid} -> SpanRecord
const PREFIX_TRACE: u8 = b't';       // Trace index: t{trace_id}{ulid} -> empty
const PREFIX_SERVICE: u8 = b'v';     // Service index: v{service_name}{ulid} -> empty
const PREFIX_ROOT: u8 = b'r';        // Root span index: r{ulid} -> empty

/// Repository provides high-throughput span storage using fjall LSM-tree.
pub struct Repository {
    keyspace: Keyspace,
    spans: PartitionHandle,
    span_count: AtomicU64,
}

impl Repository {
    /// Create a new repository at the given path.
    pub fn new(config: &StorageConfig) -> Result<Self> {
        let path = &config.wal_path;

        // Ensure parent directory exists
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)
                .with_context(|| format!("Failed to create directory: {:?}", parent))?;
        }

        // Configure fjall for high write throughput
        let fjall_config = FjallConfig::new(path);

        let keyspace = fjall_config
            .open()
            .with_context(|| format!("Failed to open fjall keyspace at {:?}", path))?;

        // Create or open the main partition
        let spans = keyspace
            .open_partition("spans", Default::default())
            .context("Failed to open spans partition")?;

        // Count existing spans for metrics
        let mut count = 0u64;
        let prefix = [PREFIX_SPAN];
        for item in spans.prefix(&prefix) {
            if item.is_ok() {
                count += 1;
            }
        }

        info!(count, "Loaded existing spans from storage");

        Ok(Self {
            keyspace,
            spans,
            span_count: AtomicU64::new(count),
        })
    }

    /// Write a span to storage with all necessary indexes.
    pub fn write_span(&self, span: &Span, resource: &Resource) -> Result<Ulid> {
        let ulid = Ulid::new();

        // Convert to SpanRecord for storage
        let record = self.convert_span(span, resource, ulid)?;

        // Serialize the record
        let record_bytes = serde_json::to_vec(&record)
            .context("Failed to serialize span record")?;

        // Build keys
        let span_key = self.make_span_key(ulid);
        let trace_key = self.make_trace_key(&record.trace_id, ulid);
        let service_key = self.make_service_key(&record.service_name, ulid);

        // Write in a batch for atomicity
        let mut batch = self.keyspace.batch();

        // Primary span data
        batch.insert(&self.spans, &span_key, &record_bytes);

        // Trace index (for querying by trace_id)
        batch.insert(&self.spans, &trace_key, &[]);

        // Service index (for querying by service_name)
        batch.insert(&self.spans, &service_key, &[]);

        // Root span index (for root-only queries)
        if record.is_root() {
            let root_key = self.make_root_key(ulid);
            batch.insert(&self.spans, &root_key, &[]);
        }

        batch.commit().context("Failed to commit span batch")?;

        self.span_count.fetch_add(1, Ordering::Relaxed);
        debug!(ulid = %ulid, trace_id = %record.trace_id, "Wrote span");

        Ok(ulid)
    }

    /// Write multiple spans in a single batch.
    pub fn write_spans(&self, spans: &[(Span, Resource)]) -> Result<Vec<Ulid>> {
        if spans.is_empty() {
            return Ok(Vec::new());
        }

        let mut batch = self.keyspace.batch();
        let mut ulids = Vec::with_capacity(spans.len());

        for (span, resource) in spans {
            let ulid = Ulid::new();
            let record = self.convert_span(span, resource, ulid)?;
            let record_bytes = serde_json::to_vec(&record)?;

            // Primary span data
            let span_key = self.make_span_key(ulid);
            batch.insert(&self.spans, &span_key, &record_bytes);

            // Trace index
            let trace_key = self.make_trace_key(&record.trace_id, ulid);
            batch.insert(&self.spans, &trace_key, &[]);

            // Service index
            let service_key = self.make_service_key(&record.service_name, ulid);
            batch.insert(&self.spans, &service_key, &[]);

            // Root span index
            if record.is_root() {
                let root_key = self.make_root_key(ulid);
                batch.insert(&self.spans, &root_key, &[]);
            }

            ulids.push(ulid);
        }

        batch.commit().context("Failed to commit span batch")?;

        self.span_count.fetch_add(spans.len() as u64, Ordering::Relaxed);
        debug!(count = spans.len(), "Wrote span batch");

        Ok(ulids)
    }

    /// Get spans by trace ID.
    pub fn get_spans_by_trace_id(&self, trace_id: &str) -> Result<Vec<SpanRecord>> {
        let prefix = self.make_trace_prefix(trace_id);
        let mut records = Vec::new();

        for item in self.spans.prefix(&prefix) {
            let (key, _) = item.context("Failed to read from trace index")?;

            // Extract ULID from index key
            let ulid = self.extract_ulid_from_trace_key(&key)?;

            // Look up the actual span data
            if let Some(record) = self.get_span_by_ulid(ulid)? {
                records.push(record);
            }
        }

        Ok(records)
    }

    /// Get spans by service name.
    pub fn get_spans_by_service(&self, service_name: &str) -> Result<Vec<SpanRecord>> {
        let prefix = self.make_service_prefix(service_name);
        let mut records = Vec::new();

        for item in self.spans.prefix(&prefix) {
            let (key, _) = item.context("Failed to read from service index")?;

            // Extract ULID from index key
            let ulid = self.extract_ulid_from_service_key(&key, service_name.len())?;

            if let Some(record) = self.get_span_by_ulid(ulid)? {
                records.push(record);
            }
        }

        Ok(records)
    }

    /// Get a span by its ULID.
    pub fn get_span_by_ulid(&self, ulid: Ulid) -> Result<Option<SpanRecord>> {
        let key = self.make_span_key(ulid);

        match self.spans.get(&key).context("Failed to get span")? {
            Some(data) => {
                let record: SpanRecord = serde_json::from_slice(&data)
                    .context("Failed to deserialize span record")?;
                Ok(Some(record))
            }
            None => Ok(None),
        }
    }

    /// Get all spans for flushing (ordered by ULID).
    pub fn get_all_spans(&self) -> Result<Vec<SpanRecord>> {
        let prefix = [PREFIX_SPAN];
        let mut records = Vec::new();

        for item in self.spans.prefix(&prefix) {
            let (_, value) = item.context("Failed to read span")?;
            let record: SpanRecord = serde_json::from_slice(&value)
                .context("Failed to deserialize span record")?;
            records.push(record);
        }

        Ok(records)
    }

    /// Get spans since a given ULID (for hot tier queries).
    pub fn get_spans_since(&self, since_ulid: Option<Ulid>) -> Result<Vec<SpanRecord>> {
        let prefix = [PREFIX_SPAN];
        let mut records = Vec::new();

        for item in self.spans.prefix(&prefix) {
            let (key, value) = item.context("Failed to read span")?;

            // Extract ULID from key
            if key.len() < 17 {
                continue;
            }
            let mut ulid_bytes = [0u8; 16];
            ulid_bytes.copy_from_slice(&key[1..17]);
            let span_ulid = Ulid::from_bytes(ulid_bytes);

            // Filter by since_ulid if provided
            if let Some(since) = since_ulid {
                if span_ulid <= since {
                    continue;
                }
            }

            let record: SpanRecord = serde_json::from_slice(&value)
                .context("Failed to deserialize span record")?;
            records.push(record);
        }

        Ok(records)
    }

    /// Get current span count.
    pub fn get_span_count(&self) -> u64 {
        self.span_count.load(Ordering::Relaxed)
    }

    /// Get approximate database size in bytes.
    pub fn get_db_size(&self) -> Result<u64> {
        Ok(self.keyspace.disk_space())
    }

    /// Delete all spans (after flushing to Parquet).
    pub fn clear_all(&self) -> Result<u64> {
        let count = self.span_count.swap(0, Ordering::Relaxed);

        // Clear all data by iterating and removing
        // Note: fjall doesn't have a bulk clear, but this is called rarely
        let prefix = [PREFIX_SPAN];
        let keys: Vec<_> = self.spans.prefix(&prefix)
            .filter_map(|item| item.ok().map(|(k, _)| k.to_vec()))
            .collect();

        let mut batch = self.keyspace.batch();
        for key in &keys {
            batch.remove(&self.spans, key);
        }

        // Also clear indexes
        for prefix in [[PREFIX_TRACE], [PREFIX_SERVICE], [PREFIX_ROOT]] {
            let keys: Vec<_> = self.spans.prefix(&prefix)
                .filter_map(|item| item.ok().map(|(k, _)| k.to_vec()))
                .collect();
            for key in &keys {
                batch.remove(&self.spans, key);
            }
        }

        batch.commit().context("Failed to clear spans")?;

        info!(count, "Cleared all spans after flush");
        Ok(count)
    }

    /// Force flush to disk.
    pub fn flush(&self) -> Result<()> {
        self.keyspace.persist(fjall::PersistMode::SyncAll)
            .context("Failed to flush keyspace")
    }

    // ========================================================================
    // Key building helpers
    // ========================================================================

    fn make_span_key(&self, ulid: Ulid) -> Vec<u8> {
        let mut key = Vec::with_capacity(17);
        key.push(PREFIX_SPAN);
        key.extend_from_slice(&ulid.to_bytes());
        key
    }

    fn make_trace_key(&self, trace_id: &str, ulid: Ulid) -> Vec<u8> {
        let mut key = Vec::with_capacity(1 + trace_id.len() + 16);
        key.push(PREFIX_TRACE);
        key.extend_from_slice(trace_id.as_bytes());
        key.extend_from_slice(&ulid.to_bytes());
        key
    }

    fn make_trace_prefix(&self, trace_id: &str) -> Vec<u8> {
        let mut key = Vec::with_capacity(1 + trace_id.len());
        key.push(PREFIX_TRACE);
        key.extend_from_slice(trace_id.as_bytes());
        key
    }

    fn make_service_key(&self, service_name: &str, ulid: Ulid) -> Vec<u8> {
        let mut key = Vec::with_capacity(1 + service_name.len() + 16);
        key.push(PREFIX_SERVICE);
        key.extend_from_slice(service_name.as_bytes());
        key.extend_from_slice(&ulid.to_bytes());
        key
    }

    fn make_service_prefix(&self, service_name: &str) -> Vec<u8> {
        let mut key = Vec::with_capacity(1 + service_name.len());
        key.push(PREFIX_SERVICE);
        key.extend_from_slice(service_name.as_bytes());
        key
    }

    fn make_root_key(&self, ulid: Ulid) -> Vec<u8> {
        let mut key = Vec::with_capacity(17);
        key.push(PREFIX_ROOT);
        key.extend_from_slice(&ulid.to_bytes());
        key
    }

    fn extract_ulid_from_trace_key(&self, key: &[u8]) -> Result<Ulid> {
        // Key format: t{trace_id (32 bytes hex)}{ulid (16 bytes)}
        // Trace ID is 32 hex chars = 32 bytes
        if key.len() < 1 + 32 + 16 {
            anyhow::bail!("Invalid trace key length");
        }
        let mut ulid_bytes = [0u8; 16];
        ulid_bytes.copy_from_slice(&key[key.len() - 16..]);
        Ok(Ulid::from_bytes(ulid_bytes))
    }

    fn extract_ulid_from_service_key(&self, key: &[u8], service_name_len: usize) -> Result<Ulid> {
        // Key format: v{service_name}{ulid (16 bytes)}
        if key.len() < 1 + service_name_len + 16 {
            anyhow::bail!("Invalid service key length");
        }
        let mut ulid_bytes = [0u8; 16];
        ulid_bytes.copy_from_slice(&key[key.len() - 16..]);
        Ok(Ulid::from_bytes(ulid_bytes))
    }

    // ========================================================================
    // Span conversion
    // ========================================================================

    fn convert_span(&self, span: &Span, resource: &Resource, ulid: Ulid) -> Result<SpanRecord> {
        // Extract trace_id and span_id as hex strings
        let trace_id = hex::encode(&span.trace_id);
        let span_id = hex::encode(&span.span_id);
        let parent_span_id = hex::encode(&span.parent_span_id);

        // Extract service name from resource attributes
        let service_name = resource
            .attributes
            .iter()
            .find(|kv| kv.key == "service.name")
            .and_then(|kv| kv.value.as_ref())
            .and_then(|v| self.any_value_to_string(v))
            .unwrap_or_else(|| "unknown".to_string());

        // Convert timestamps
        let start_time = self.nanos_to_datetime(span.start_time_unix_nano);
        let end_time = self.nanos_to_datetime(span.end_time_unix_nano);
        let duration_ns = (span.end_time_unix_nano as i64) - (span.start_time_unix_nano as i64);

        // Convert status
        let (status_code, status_message) = match &span.status {
            Some(status) => {
                let code = match StatusCode::try_from(status.code).unwrap_or(StatusCode::Unset) {
                    StatusCode::Unset => "UNSET",
                    StatusCode::Ok => "OK",
                    StatusCode::Error => "ERROR",
                };
                (code.to_string(), status.message.clone())
            }
            None => ("UNSET".to_string(), String::new()),
        };

        // Convert span kind
        let span_kind = match SpanKind::try_from(span.kind).unwrap_or(SpanKind::Unspecified) {
            SpanKind::Unspecified => "UNSPECIFIED",
            SpanKind::Internal => "INTERNAL",
            SpanKind::Server => "SERVER",
            SpanKind::Client => "CLIENT",
            SpanKind::Producer => "PRODUCER",
            SpanKind::Consumer => "CONSUMER",
        }
        .to_string();

        // Convert attributes to JSON
        let attributes_json = self.key_values_to_json(&span.attributes)?;
        let resource_attributes_json = self.key_values_to_json(&resource.attributes)?;

        // Convert events to JSON
        let events_json = self.events_to_json(&span.events)?;

        Ok(SpanRecord {
            ulid: ulid.to_string(),
            trace_id,
            span_id,
            parent_span_id,
            name: span.name.clone(),
            service_name,
            span_kind,
            start_time,
            end_time,
            duration_ns,
            status_code,
            status_message,
            attributes_json,
            resource_attributes_json,
            events_json,
        })
    }

    fn nanos_to_datetime(&self, nanos: u64) -> DateTime<Utc> {
        let secs = (nanos / 1_000_000_000) as i64;
        let nsecs = (nanos % 1_000_000_000) as u32;
        Utc.timestamp_opt(secs, nsecs).unwrap()
    }

    fn any_value_to_string(&self, value: &AnyValue) -> Option<String> {
        use crate::proto::opentelemetry::proto::common::v1::any_value::Value;
        match &value.value {
            Some(Value::StringValue(s)) => Some(s.clone()),
            Some(Value::BoolValue(b)) => Some(b.to_string()),
            Some(Value::IntValue(i)) => Some(i.to_string()),
            Some(Value::DoubleValue(d)) => Some(d.to_string()),
            _ => None,
        }
    }

    fn any_value_to_json(&self, value: &AnyValue) -> serde_json::Value {
        use crate::proto::opentelemetry::proto::common::v1::any_value::Value;
        match &value.value {
            Some(Value::StringValue(s)) => serde_json::Value::String(s.clone()),
            Some(Value::BoolValue(b)) => serde_json::Value::Bool(*b),
            Some(Value::IntValue(i)) => serde_json::json!(*i),
            Some(Value::DoubleValue(d)) => serde_json::json!(*d),
            Some(Value::ArrayValue(arr)) => {
                let items: Vec<_> = arr.values.iter().map(|v| self.any_value_to_json(v)).collect();
                serde_json::Value::Array(items)
            }
            Some(Value::KvlistValue(kvlist)) => {
                let mut map = serde_json::Map::new();
                for kv in &kvlist.values {
                    if let Some(v) = &kv.value {
                        map.insert(kv.key.clone(), self.any_value_to_json(v));
                    }
                }
                serde_json::Value::Object(map)
            }
            Some(Value::BytesValue(b)) => serde_json::Value::String(hex::encode(b)),
            None => serde_json::Value::Null,
        }
    }

    fn key_values_to_json(
        &self,
        kvs: &[crate::proto::opentelemetry::proto::common::v1::KeyValue],
    ) -> Result<String> {
        let mut map = serde_json::Map::new();
        for kv in kvs {
            if let Some(v) = &kv.value {
                map.insert(kv.key.clone(), self.any_value_to_json(v));
            }
        }
        Ok(serde_json::to_string(&serde_json::Value::Object(map))?)
    }

    fn events_to_json(
        &self,
        events: &[crate::proto::opentelemetry::proto::trace::v1::span::Event],
    ) -> Result<String> {
        let events_json: Vec<_> = events
            .iter()
            .map(|e| {
                let attrs = self.key_values_to_json(&e.attributes).unwrap_or_default();
                serde_json::json!({
                    "name": e.name,
                    "time_unix_nano": e.time_unix_nano,
                    "attributes": serde_json::from_str::<serde_json::Value>(&attrs).unwrap_or_default()
                })
            })
            .collect();
        Ok(serde_json::to_string(&events_json)?)
    }
}
