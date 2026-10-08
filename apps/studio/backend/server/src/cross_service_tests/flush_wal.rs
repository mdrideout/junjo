//! Flushing ingestion's write-ahead log to cold Parquet through the backend's
//! ingestion client.

use opentelemetry_proto::tonic::trace::v1::Span;

use super::{harness, otlp};
use crate::features::otel_spans::repository;
use crate::features::parquet_indexer::scan::scan_parquet_files;
use crate::test_support::{TestApp, test_app};

const SERVICE: &str = "svc-flush-wal";
const TRACE_ID: &str = "0af7651916cd43dd8448eb211c80319c";
const SPAN_IDS: [&str; 3] = ["b7ad6b7169203331", "b7ad6b7169203332", "b7ad6b7169203333"];

/// One span per identifier, all in one trace.
fn spans() -> Vec<Span> {
    SPAN_IDS
        .iter()
        .map(|span_id| otlp::span(TRACE_ID, span_id, "span"))
        .collect()
}

/// The cold Parquet files ingestion has written.
fn cold_files(app: &TestApp) -> Vec<String> {
    scan_parquet_files(&app.parquet_directory)
        .into_iter()
        .map(|file| file.path)
        .collect()
}

#[tokio::test]
async fn flushing_an_empty_log_succeeds_every_time_and_writes_no_file() {
    let (app, _ingestion) = harness::start().await;

    assert_eq!(app.state.ingestion.flush_wal().await, Ok(()));
    assert_eq!(app.state.ingestion.flush_wal().await, Ok(()));

    assert_eq!(cold_files(&app), Vec::<String>::new());
}

#[tokio::test]
async fn a_flush_moves_unflushed_spans_from_the_hot_snapshot_to_one_cold_file() {
    let (app, ingestion) = harness::start().await;
    let client = &app.state.ingestion;
    ingestion
        .export(otlp::export_request(SERVICE, spans()))
        .await;

    // Before the flush the spans are in the hot snapshot.
    let unflushed = client.query_context().await;
    assert!(unflushed.hot_snapshot_path.is_some());
    assert_eq!(unflushed.recent_cold_paths, Vec::<String>::new());

    assert_eq!(client.flush_wal().await, Ok(()));

    // After it there is no hot snapshot, and the one cold file on disk is
    // the one ingestion reports as recently flushed.
    let flushed = client.query_context().await;
    assert_eq!(flushed.hot_snapshot_path, None);
    assert_eq!(flushed.recent_cold_paths.len(), 1);
    assert_eq!(flushed.recent_cold_paths, cold_files(&app));

    // A second flush has nothing to do and changes nothing.
    assert_eq!(client.flush_wal().await, Ok(()));
    assert_eq!(client.query_context().await, flushed);
    assert_eq!(cold_files(&app), flushed.recent_cold_paths);
}

#[tokio::test]
async fn concurrent_flushes_all_succeed_and_write_the_spans_once() {
    let (app, ingestion) = harness::start().await;
    let client = &app.state.ingestion;
    ingestion
        .export(otlp::export_request(SERVICE, spans()))
        .await;

    let outcomes = tokio::join!(client.flush_wal(), client.flush_wal(), client.flush_wal());

    assert_eq!(outcomes, (Ok(()), Ok(()), Ok(())));
    assert_eq!(cold_files(&app).len(), 1);
    let found = repository::trace_spans(&app.state, TRACE_ID).await.unwrap();
    let mut span_ids: Vec<&str> = found.iter().map(|span| span.span_id.as_str()).collect();
    span_ids.sort();
    assert_eq!(span_ids, SPAN_IDS);
}

#[tokio::test]
async fn a_flush_that_cannot_reach_ingestion_is_an_error() {
    // A test application's ingestion client points at a port nothing listens
    // on.
    let app = test_app();

    let error = app.state.ingestion.flush_wal().await.unwrap_err();

    assert!(error.starts_with("FlushWAL RPC failed"), "{error}");
}
