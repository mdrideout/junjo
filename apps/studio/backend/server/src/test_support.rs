//! Shared fixtures for tests.

use std::collections::VecDeque;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use chrono::DateTime;
use datafusion::arrow::array::{
    ArrayRef, Int8Array, Int64Array, RecordBatch, StringArray, TimestampNanosecondArray,
    UInt32Array,
};
use datafusion::arrow::datatypes::{DataType, Field, Schema, TimeUnit};
use datafusion::parquet::arrow::ArrowWriter;
use datafusion::parquet::basic::Compression;
use datafusion::parquet::file::properties::WriterProperties;
use rusqlite::Connection;
use tokio::net::TcpListener;
use tonic::transport::Server;
use tonic::transport::server::TcpIncoming;
use tonic::{Request, Response, Status};

use crate::config::DataFusionConfig;
use crate::db;
use crate::db::metadata;
use crate::features::auth::session_store::SqliteSessionStore;
use crate::features::config::ConfigResponse;
use crate::features::otel_spans::query::{QueryEngine, Span};
use crate::features::parquet_indexer::reader::summarize_parquet_file;
use crate::features::parquet_indexer::{Indexer, IndexerHandle, IndexerSettings};
use crate::features::span_ingestion::IngestionClient;
use crate::proto::internal_ingestion_service_server::{
    InternalIngestionService, InternalIngestionServiceServer,
};
use crate::proto::{
    FlushWalRequest, FlushWalResponse, PrepareHotSnapshotRequest, PrepareHotSnapshotResponse,
};
use crate::state::AppState;

pub const INTERNAL_TOKEN: &str = "test-internal-grpc-token-32-bytes-long";

/// One span as ingestion would store it.
#[derive(Debug, Clone)]
pub struct TestSpan {
    pub span_id: String,
    pub trace_id: String,
    pub parent_span_id: Option<String>,
    pub service_name: String,
    pub name: String,
    pub span_kind: i8,
    pub start_time_ns: i64,
    pub end_time_ns: i64,
    pub status_code: i8,
    pub status_message: Option<String>,
    pub attributes: String,
    pub events: String,
    pub links: String,
    pub trace_flags: u32,
    pub trace_state: Option<String>,
    pub dropped_attributes_count: u32,
    pub dropped_events_count: u32,
    pub dropped_links_count: u32,
    pub resource_attributes: String,
    pub resource_dropped_attributes_count: u32,
}

impl TestSpan {
    pub fn new(trace_id: &str, span_id: &str, service_name: &str) -> Self {
        Self {
            span_id: span_id.to_string(),
            trace_id: trace_id.to_string(),
            parent_span_id: None,
            service_name: service_name.to_string(),
            name: "span".to_string(),
            span_kind: 1,
            start_time_ns: 1_736_937_000_000_000_000,
            end_time_ns: 1_736_937_001_000_000_000,
            status_code: 0,
            status_message: None,
            attributes: "{}".to_string(),
            events: "[]".to_string(),
            links: "[]".to_string(),
            trace_flags: 0,
            trace_state: None,
            dropped_attributes_count: 0,
            dropped_events_count: 0,
            dropped_links_count: 0,
            resource_attributes: r#"{"service.name":"test"}"#.to_string(),
            resource_dropped_attributes_count: 0,
        }
    }

    /// The stored form of one span given in the raw span API's shape, which is
    /// how the shared telemetry fixtures describe spans.
    pub fn from_api_span(span: &serde_json::Value) -> Self {
        let text = |name: &str| span[name].as_str().expect(name).to_string();
        let optional_text = |name: &str| span[name].as_str().map(str::to_string);
        let count = |name: &str| u32::try_from(span[name].as_u64().expect(name)).expect(name);
        let nanoseconds = |name: &str| {
            DateTime::parse_from_rfc3339(span[name].as_str().expect(name))
                .expect(name)
                .timestamp_nanos_opt()
                .expect(name)
        };
        let span_kind = match span["kind"].as_str().expect("kind") {
            "UNSPECIFIED" => 0,
            "INTERNAL" => 1,
            "SERVER" => 2,
            "CLIENT" => 3,
            "PRODUCER" => 4,
            "CONSUMER" => 5,
            other => panic!("unknown span kind {other}"),
        };
        Self {
            span_id: text("span_id"),
            trace_id: text("trace_id"),
            parent_span_id: optional_text("parent_span_id"),
            service_name: text("service_name"),
            name: text("name"),
            span_kind,
            start_time_ns: nanoseconds("start_time"),
            end_time_ns: nanoseconds("end_time"),
            status_code: text("status_code").parse().expect("status_code"),
            // Ingestion stores an empty status message as null.
            status_message: optional_text("status_message").filter(|message| !message.is_empty()),
            attributes: span["attributes_json"].to_string(),
            events: span["events_json"].to_string(),
            links: span["links_json"].to_string(),
            trace_flags: count("trace_flags"),
            trace_state: optional_text("trace_state"),
            dropped_attributes_count: count("dropped_attributes_count"),
            dropped_events_count: count("dropped_events_count"),
            dropped_links_count: count("dropped_links_count"),
            resource_attributes: span["resource_attributes_json"].to_string(),
            resource_dropped_attributes_count: count("resource_dropped_attributes_count"),
        }
    }

    pub fn attributes(mut self, attributes: &str) -> Self {
        self.attributes = attributes.to_string();
        self
    }

    pub fn times(mut self, start_time_ns: i64, end_time_ns: i64) -> Self {
        self.start_time_ns = start_time_ns;
        self.end_time_ns = end_time_ns;
        self
    }

    pub fn name(mut self, name: &str) -> Self {
        self.name = name.to_string();
        self
    }

    pub fn parent(mut self, parent_span_id: &str) -> Self {
        self.parent_span_id = Some(parent_span_id.to_string());
        self
    }
}

/// The shared telemetry fixtures in one directory under
/// `contracts/telemetry/fixtures`, as `(name, fixture)` in name order. Every
/// fixture must target the active telemetry contract version.
pub fn telemetry_fixtures(directory: &str) -> Vec<(String, serde_json::Value)> {
    // The workspace sits four directories below the monorepo root.
    let contract = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../../contracts/telemetry");
    let active_version: u64 = std::fs::read_to_string(contract.join("VERSION"))
        .expect("the telemetry contract version")
        .trim()
        .parse()
        .expect("a numeric telemetry contract version");

    let directory = contract.join("fixtures").join(directory);
    let mut paths: Vec<PathBuf> = std::fs::read_dir(&directory)
        .unwrap_or_else(|error| panic!("cannot list {}: {error}", directory.display()))
        .map(|entry| entry.expect("a directory entry").path())
        .filter(|path| {
            path.extension()
                .is_some_and(|extension| extension == "json")
        })
        .collect();
    paths.sort();
    assert!(!paths.is_empty(), "no fixtures in {}", directory.display());

    paths
        .into_iter()
        .map(|path| {
            let name = path
                .file_stem()
                .expect("a file name")
                .to_string_lossy()
                .into_owned();
            let text = std::fs::read_to_string(&path)
                .unwrap_or_else(|error| panic!("cannot read {}: {error}", path.display()));
            let fixture: serde_json::Value = serde_json::from_str(&text)
                .unwrap_or_else(|error| panic!("cannot parse {}: {error}", path.display()));
            assert_eq!(
                fixture["contract_version"].as_u64(),
                Some(active_version),
                "fixture {name} does not target the active telemetry contract"
            );
            (name, fixture)
        })
        .collect()
}

/// Order spans in the raw API's JSON shape by identity, so two sets of spans
/// compare independently of query order.
fn by_identity(mut spans: Vec<serde_json::Value>) -> Vec<serde_json::Value> {
    spans.sort_by_key(|span| {
        (
            span["trace_id"].as_str().unwrap().to_string(),
            span["span_id"].as_str().unwrap().to_string(),
        )
    });
    spans
}

/// Queried spans as the raw API serializes them, ordered by identity.
pub fn api_spans(spans: &[Span]) -> Vec<serde_json::Value> {
    by_identity(
        spans
            .iter()
            .map(|span| serde_json::to_value(span).unwrap())
            .collect(),
    )
}

/// The spans of one shared telemetry fixture, ordered by identity. With a
/// span type, only the spans of that Junjo type.
pub fn case_spans(case: &serde_json::Value, span_type: Option<&str>) -> Vec<serde_json::Value> {
    by_identity(
        case["spans"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|span| {
                span_type.is_none()
                    || span["attributes_json"]["junjo.span_type"].as_str() == span_type
            })
            .cloned()
            .collect(),
    )
}

/// The stored span schema, as written by the ingestion service.
pub fn span_schema() -> Arc<Schema> {
    let timestamp = DataType::Timestamp(TimeUnit::Nanosecond, Some("UTC".into()));
    Arc::new(Schema::new(vec![
        Field::new("span_id", DataType::Utf8, false),
        Field::new("trace_id", DataType::Utf8, false),
        Field::new("parent_span_id", DataType::Utf8, true),
        Field::new("service_name", DataType::Utf8, false),
        Field::new("name", DataType::Utf8, false),
        Field::new("span_kind", DataType::Int8, false),
        Field::new("start_time", timestamp.clone(), false),
        Field::new("end_time", timestamp, false),
        Field::new("duration_ns", DataType::Int64, false),
        Field::new("status_code", DataType::Int8, false),
        Field::new("status_message", DataType::Utf8, true),
        Field::new("attributes", DataType::Utf8, false),
        Field::new("events", DataType::Utf8, false),
        Field::new("links", DataType::Utf8, false),
        Field::new("trace_flags", DataType::UInt32, false),
        Field::new("trace_state", DataType::Utf8, true),
        Field::new("dropped_attributes_count", DataType::UInt32, false),
        Field::new("dropped_events_count", DataType::UInt32, false),
        Field::new("dropped_links_count", DataType::UInt32, false),
        Field::new("resource_attributes", DataType::Utf8, false),
        Field::new("resource_dropped_attributes_count", DataType::UInt32, false),
    ]))
}

/// Write spans to a Parquet file with ingestion's schema and compression.
pub fn write_span_parquet(path: &Path, spans: &[TestSpan]) {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).unwrap();
    }
    let text = |value: fn(&TestSpan) -> &str| -> ArrayRef {
        Arc::new(StringArray::from_iter_values(spans.iter().map(value)))
    };
    let optional_text = |value: fn(&TestSpan) -> Option<&str>| -> ArrayRef {
        Arc::new(StringArray::from_iter(spans.iter().map(value)))
    };
    let small_integers = |value: fn(&TestSpan) -> i8| -> ArrayRef {
        Arc::new(Int8Array::from_iter_values(spans.iter().map(value)))
    };
    let counts = |value: fn(&TestSpan) -> u32| -> ArrayRef {
        Arc::new(UInt32Array::from_iter_values(spans.iter().map(value)))
    };
    let timestamps = |value: fn(&TestSpan) -> i64| -> ArrayRef {
        Arc::new(
            TimestampNanosecondArray::from_iter_values(spans.iter().map(value))
                .with_timezone("UTC"),
        )
    };
    let columns: Vec<ArrayRef> = vec![
        text(|span| &span.span_id),
        text(|span| &span.trace_id),
        optional_text(|span| span.parent_span_id.as_deref()),
        text(|span| &span.service_name),
        text(|span| &span.name),
        small_integers(|span| span.span_kind),
        timestamps(|span| span.start_time_ns),
        timestamps(|span| span.end_time_ns),
        Arc::new(Int64Array::from_iter_values(
            spans
                .iter()
                .map(|span| span.end_time_ns - span.start_time_ns),
        )),
        small_integers(|span| span.status_code),
        optional_text(|span| span.status_message.as_deref()),
        text(|span| &span.attributes),
        text(|span| &span.events),
        text(|span| &span.links),
        counts(|span| span.trace_flags),
        optional_text(|span| span.trace_state.as_deref()),
        counts(|span| span.dropped_attributes_count),
        counts(|span| span.dropped_events_count),
        counts(|span| span.dropped_links_count),
        text(|span| &span.resource_attributes),
        counts(|span| span.resource_dropped_attributes_count),
    ];
    let batch = RecordBatch::try_new(span_schema(), columns).unwrap();
    let properties = WriterProperties::builder()
        .set_compression(Compression::LZ4_RAW)
        .build();
    let file = std::fs::File::create(path).unwrap();
    let mut writer = ArrowWriter::try_new(file, span_schema(), Some(properties)).unwrap();
    writer.write(&batch).unwrap();
    writer.close().unwrap();
}

pub fn datafusion_config(directory: &Path) -> DataFusionConfig {
    DataFusionConfig {
        target_partitions: 1,
        batch_size: 4096,
        parquet_pruning: true,
        spill_enabled: true,
        spill_pool_bytes: 192 * 1024 * 1024,
        spill_path: directory.join("spill"),
    }
}

/// A complete application over temporary databases. Ingestion is unreachable,
/// so queries exercise the cold-only path. A test that needs the hot snapshot
/// or the recent-cold bridge replaces `state.ingestion` with
/// `ingestion_reporting`.
pub struct TestApp {
    pub state: AppState,
    /// The metadata index writer that the indexer thread would own.
    pub metadata_writer: Connection,
    pub parquet_directory: PathBuf,
    _directory: tempfile::TempDir,
}

impl TestApp {
    /// Start a real indexer thread over this application's cold storage and
    /// metadata index, and let requests reach it. It polls so rarely that
    /// only a request starts a cycle.
    pub fn spawn_indexer(&mut self) -> Indexer {
        let directory = self._directory.path();
        let metadata = db::open_metadata_db(&directory.join("sqlite/metadata.db")).unwrap();
        let indexer = Indexer::spawn(
            IndexerSettings {
                parquet_storage_path: self.parquet_directory.clone(),
                poll_interval: std::time::Duration::from_secs(3600),
                batch_size: 10,
                read_batch_rows: 4096,
            },
            metadata.writer,
        )
        .unwrap();
        self.state.indexer = indexer.handle();
        indexer
    }

    /// Write a cold Parquet file that the index does not cover, as a flush the
    /// indexer has not reached yet. Returns its path.
    pub fn write_cold_file(&self, name: &str, spans: &[TestSpan]) -> String {
        let path = self.parquet_directory.join(name);
        write_span_parquet(&path, spans);
        path.to_str().unwrap().to_string()
    }

    /// Write a cold Parquet file and index it, as the indexer thread would.
    /// Returns its path.
    pub fn index_cold_file(&mut self, name: &str, spans: &[TestSpan]) -> String {
        let file_path = self.write_cold_file(name, spans);
        let size_bytes = std::fs::metadata(&file_path).unwrap().len();
        let summary = summarize_parquet_file(Path::new(&file_path), size_bytes, 4096).unwrap();
        metadata::index_file(&mut self.metadata_writer, &summary).unwrap();
        file_path
    }

    /// Write a hot snapshot file beside the cold storage directory. Returns
    /// its path.
    pub fn write_hot_snapshot(&self, spans: &[TestSpan]) -> String {
        let path = self
            .parquet_directory
            .with_file_name("hot_snapshot.parquet");
        write_span_parquet(&path, spans);
        path.to_str().unwrap().to_string()
    }
}

/// A stand-in for the ingestion service's internal API.
struct StandInIngestion {
    /// The answers to snapshot requests, in turn. The last one is repeated.
    snapshots: Mutex<VecDeque<PrepareHotSnapshotResponse>>,
    /// `None` means the stand-in does not flush. Every flush gets the same
    /// answer.
    flush: Option<FlushWalResponse>,
}

#[tonic::async_trait]
impl InternalIngestionService for StandInIngestion {
    async fn prepare_hot_snapshot(
        &self,
        _request: Request<PrepareHotSnapshotRequest>,
    ) -> Result<Response<PrepareHotSnapshotResponse>, Status> {
        let mut snapshots = self.snapshots.lock().unwrap();
        let snapshot = if snapshots.len() > 1 {
            snapshots.pop_front()
        } else {
            snapshots.front().cloned()
        };
        Ok(Response::new(snapshot.expect("the stand-in has an answer")))
    }

    async fn flush_wal(
        &self,
        _request: Request<FlushWalRequest>,
    ) -> Result<Response<FlushWalResponse>, Status> {
        match &self.flush {
            Some(response) => Ok(Response::new(response.clone())),
            None => Err(Status::unimplemented("the stand-in does not flush")),
        }
    }
}

/// Serve a stand-in on an ephemeral port and return a client for it. The
/// server stops with the calling test's runtime.
async fn serve_stand_in(stand_in: StandInIngestion) -> IngestionClient {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let port = listener.local_addr().unwrap().port();
    tokio::spawn(
        Server::builder()
            .add_service(InternalIngestionServiceServer::new(stand_in))
            .serve_with_incoming(TcpIncoming::from(listener)),
    );
    IngestionClient::new("127.0.0.1", port, INTERNAL_TOKEN).unwrap()
}

/// A client for a stand-in ingestion service that reports `hot_snapshot` as
/// the snapshot of unflushed spans and `recent_cold_paths` as the flushed
/// files not yet indexed.
pub async fn ingestion_reporting(
    hot_snapshot: Option<&str>,
    recent_cold_paths: &[String],
) -> IngestionClient {
    ingestion_reporting_in_turn(&[(hot_snapshot, recent_cold_paths)]).await
}

/// A client for a stand-in ingestion service that gives each of these
/// answers once, in turn, and then repeats the last one. An answer is a hot
/// snapshot and the recent-cold files, as `ingestion_reporting` takes them.
pub async fn ingestion_reporting_in_turn(answers: &[(Option<&str>, &[String])]) -> IngestionClient {
    let snapshots = answers
        .iter()
        .map(
            |(hot_snapshot, recent_cold_paths)| PrepareHotSnapshotResponse {
                snapshot_path: hot_snapshot.unwrap_or_default().to_string(),
                // The backend reads only whether the snapshot has rows.
                row_count: i64::from(hot_snapshot.is_some()),
                file_size_bytes: 0,
                success: true,
                error_message: String::new(),
                recent_cold_paths: recent_cold_paths.to_vec(),
            },
        )
        .collect();
    serve_stand_in(StandInIngestion {
        snapshots: Mutex::new(snapshots),
        flush: None,
    })
    .await
}

/// A client for a stand-in ingestion service whose flush succeeds, or fails
/// with the given message. It has no unflushed spans.
pub async fn ingestion_flushing(outcome: Result<(), &str>) -> IngestionClient {
    serve_stand_in(StandInIngestion {
        snapshots: Mutex::new(VecDeque::from([PrepareHotSnapshotResponse {
            success: true,
            ..Default::default()
        }])),
        flush: Some(FlushWalResponse {
            success: outcome.is_ok(),
            error_message: outcome.err().unwrap_or_default().to_string(),
        }),
    })
    .await
}

pub fn test_app() -> TestApp {
    let directory = tempfile::tempdir().unwrap();
    let application_db =
        db::open_application_db(&directory.path().join("sqlite/junjo.db")).unwrap();
    let metadata = db::open_metadata_db(&directory.path().join("sqlite/metadata.db")).unwrap();
    let state = AppState {
        application_db: application_db.clone(),
        metadata: metadata.reader,
        session_store: SqliteSessionStore::new(application_db),
        // Port 9 (discard) is not listening: the call fails fast.
        ingestion: IngestionClient::new("127.0.0.1", 9, INTERNAL_TOKEN).unwrap(),
        query: Arc::new(QueryEngine::new(&datafusion_config(directory.path())).unwrap()),
        // No indexer thread runs: tests index through `metadata_writer`.
        indexer: IndexerHandle::disconnected(),
        deployment: Arc::new(ConfigResponse {
            environment: "development",
            otlp_endpoint: "grpc://localhost:26155".to_string(),
        }),
        ui: None,
    };
    TestApp {
        state,
        metadata_writer: metadata.writer,
        parquet_directory: directory.path().join("spans/parquet"),
        _directory: directory,
    }
}
