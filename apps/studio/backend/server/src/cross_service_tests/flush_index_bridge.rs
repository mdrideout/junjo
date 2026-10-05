//! The gap between a flush and the indexer.
//!
//! After a flush, spans exist only in a new cold file. Until the indexer
//! reaches that file the metadata index does not know the trace, and the
//! write-ahead log is empty, so there is no hot snapshot either. Ingestion
//! closes the gap by reporting the file as recently flushed (ingestion
//! ADR-002).

use std::collections::HashSet;

use opentelemetry_proto::tonic::trace::v1::Span;
use opentelemetry_proto::tonic::trace::v1::span::SpanKind;

use super::{harness, otlp};
use crate::db::metadata;
use crate::features::otel_spans::repository;

const SERVICE: &str = "svc-flush-index-bridge";
const TRACE_ID: &str = "4bf92f3577b34da6a3ce929d0e0e4736";
const ROOT_SPAN_ID: &str = "00f067aa0ba902b7";
const CHILD_SPAN_ID: &str = "00f067aa0ba902b8";

#[tokio::test]
async fn a_flushed_trace_that_is_not_indexed_yet_is_found_through_the_recent_cold_files() {
    let (app, ingestion) = harness::start().await;
    let root = Span {
        kind: SpanKind::Server as i32,
        ..otlp::span(TRACE_ID, ROOT_SPAN_ID, "root-span")
    };
    let child = Span {
        parent_span_id: otlp::hex_bytes(ROOT_SPAN_ID),
        start_time_unix_nano: otlp::START_NS + 1_000,
        end_time_unix_nano: otlp::START_NS + 1_001_000,
        ..otlp::span(TRACE_ID, CHILD_SPAN_ID, "child-span")
    };
    ingestion
        .export(otlp::export_request(SERVICE, vec![root, child]))
        .await;

    // The flush empties the write-ahead log into one new cold file.
    assert_eq!(app.state.ingestion.flush_wal().await, Ok(()));

    // The metadata index does not know the trace.
    let indexed = app
        .state
        .metadata
        .call(|connection| metadata::file_paths_for_trace(connection, TRACE_ID))
        .await
        .unwrap();
    assert_eq!(indexed, Vec::<String>::new());

    // Ingestion reports no hot snapshot, and the new file as recently flushed.
    let context = app.state.ingestion.query_context().await;
    assert_eq!(context.hot_snapshot_path, None);
    assert_eq!(context.recent_cold_paths.len(), 1);
    let cold_file = std::fs::metadata(&context.recent_cold_paths[0]).unwrap();
    assert!(cold_file.len() > 0);

    // The trace query still finds every span.
    let spans = repository::trace_spans(&app.state, TRACE_ID).await.unwrap();
    assert_eq!(spans.len(), 2);
    let span_ids: HashSet<&str> = spans.iter().map(|span| span.span_id.as_str()).collect();
    assert_eq!(span_ids, HashSet::from([ROOT_SPAN_ID, CHILD_SPAN_ID]));
    for span in &spans {
        assert_eq!(span.trace_id, TRACE_ID);
    }
}
