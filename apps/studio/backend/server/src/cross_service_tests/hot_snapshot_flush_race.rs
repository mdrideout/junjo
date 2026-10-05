//! A trace query that races a flush.
//!
//! A flush moves the write-ahead log into a cold file and deletes the log's
//! segments. A query's snapshot request that arrives during the flush is
//! answered after it, when the log is empty. If ingestion did not report the
//! new cold file in that answer, the backend would return nothing for a
//! trace that was just ingested. Ingestion records the file while it still
//! holds the log, so a query finds the spans in the snapshot or in the cold
//! file, never in neither.
//!
//! Each test runs one query against one flush. The harness turns snapshot
//! reuse off, and two queries would then also race each other for the
//! snapshot file.

use std::collections::HashSet;

use opentelemetry_proto::tonic::trace::v1::Span;

use super::harness::{self, Ingestion};
use super::otlp;
use crate::db::metadata;
use crate::features::otel_spans::query;
use crate::features::otel_spans::repository;
use crate::test_support::TestApp;

const SERVICE: &str = "svc-hot-cold-race";
const TRACE_ID: &str = "c2f5b6e0a8d14f3e9b7a6d5c4e3f2a1b";
/// Enough spans, in exports of the size an SDK batches, that the flush holds
/// the log for a few milliseconds.
const EXPORTS: u64 = 25;
const SPANS_PER_EXPORT: u64 = 200;

/// Send the trace to ingestion and check that the metadata index does not
/// know it. No indexer runs in these tests, so only the hot snapshot and the
/// recent-cold bridge can serve the trace. Returns the span identifiers that
/// were sent.
async fn ingest_trace(app: &TestApp, ingestion: &Ingestion) -> HashSet<String> {
    let payload = "x".repeat(256);
    let mut span_ids = HashSet::new();
    for export in 0..EXPORTS {
        let spans = (0..SPANS_PER_EXPORT)
            .map(|index| {
                let span_id = format!("{:016x}", export * SPANS_PER_EXPORT + index + 1);
                let span = Span {
                    start_time_unix_nano: otlp::START_NS + index * 1_000,
                    end_time_unix_nano: otlp::START_NS + index * 1_000 + 1_000_000,
                    attributes: vec![otlp::text_attribute("payload", &payload)],
                    ..otlp::span(TRACE_ID, &span_id, &format!("span-{index}"))
                };
                span_ids.insert(span_id);
                span
            })
            .collect();
        ingestion.export(otlp::export_request(SERVICE, spans)).await;
    }

    let indexed = app
        .state
        .metadata
        .call(|connection| metadata::file_paths_for_trace(connection, TRACE_ID))
        .await
        .unwrap();
    assert_eq!(indexed, Vec::<String>::new());
    span_ids
}

/// Assert that a query returned every span of the trace exactly once.
fn assert_every_span_once(spans: Vec<query::Span>, expected_span_ids: HashSet<String>) {
    assert_eq!(spans.len(), expected_span_ids.len());
    for span in &spans {
        assert_eq!(span.trace_id, TRACE_ID);
    }
    let span_ids: HashSet<String> = spans.into_iter().map(|span| span.span_id).collect();
    assert_eq!(span_ids, expected_span_ids);
}

#[tokio::test]
async fn a_trace_query_sent_while_a_flush_holds_the_log_returns_every_span_once() {
    let (app, ingestion) = harness::start().await;
    let expected_span_ids = ingest_trace(&app, &ingestion).await;

    let flush = tokio::spawn({
        let client = app.state.ingestion.clone();
        async move { client.flush_wal().await }
    });
    // Ingestion creates the cold file's directory at the start of the flush,
    // while it holds the log. A snapshot request sent from then on is
    // answered after the flush, when the log is empty.
    let flush_is_writing = || {
        std::fs::read_dir(&app.parquet_directory)
            .unwrap()
            .next()
            .is_some()
    };
    while !flush_is_writing() && !flush.is_finished() {
        tokio::task::yield_now().await;
    }
    let spans = repository::trace_spans(&app.state, TRACE_ID).await.unwrap();

    assert_eq!(flush.await.unwrap(), Ok(()));
    assert_every_span_once(spans, expected_span_ids);
}

#[tokio::test]
async fn a_trace_query_sent_together_with_a_flush_returns_every_span_once() {
    let (app, ingestion) = harness::start().await;
    let expected_span_ids = ingest_trace(&app, &ingestion).await;

    // Both requests are in flight at once, and ingestion decides which takes
    // the log first. The snapshot request usually does: the flush waits for
    // it and the query reads the hot snapshot, the opposite order to the
    // test above.
    let (flushed, spans) = tokio::join!(
        app.state.ingestion.flush_wal(),
        repository::trace_spans(&app.state, TRACE_ID),
    );

    assert_eq!(flushed, Ok(()));
    assert_every_span_once(spans.unwrap(), expected_span_ids);
}
