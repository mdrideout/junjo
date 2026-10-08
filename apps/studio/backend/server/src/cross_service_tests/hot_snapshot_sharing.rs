//! Concurrent trace queries while ingestion replaces the hot snapshot.
//!
//! Ingestion writes the hot snapshot to one path and replaces it for the
//! first request after its reuse period. A query that was given the path
//! earlier may still be reading it, and then fails. Such a query asks
//! ingestion again and runs once more (ingestion ADR-002), so every query
//! returns the whole trace.
//!
//! This test keeps the deployment's reuse period. A shorter one would have
//! the snapshot replaced under the second run as well.

use std::collections::HashSet;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use opentelemetry_proto::tonic::trace::v1::Span;

use super::harness;
use super::otlp;
use crate::features::otel_spans::repository;

const SERVICE: &str = "svc-snapshot-sharing";
const TRACE_ID: &str = "a1b2c3d4e5f60718293a4b5c6d7e8f90";
const TRACE_EXPORTS: u64 = 10;
const SPANS_PER_EXPORT: u64 = 200;
/// What a deployment's ingestion reuses one snapshot for.
const SNAPSHOT_REUSE: Duration = Duration::from_secs(1);
const READERS: usize = 8;
/// Long enough that ingestion replaces the snapshot under the readers
/// several times.
const READING: Duration = Duration::from_secs(6);

fn span_id(number: u64) -> String {
    format!("{number:016x}")
}

fn span_with_payload(trace_id: &str, span_id: &str, name: &str) -> Span {
    Span {
        attributes: vec![otlp::text_attribute("payload", &"x".repeat(256))],
        ..otlp::span(trace_id, span_id, name)
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn concurrent_trace_queries_return_the_whole_trace_while_the_snapshot_is_replaced() {
    let (app, ingestion) = harness::start_with_snapshot_reuse(SNAPSHOT_REUSE).await;
    let ingestion = Arc::new(ingestion);

    // The trace every reader asks for. Nothing flushes, so it stays in the
    // write-ahead log and is read from the hot snapshot.
    let mut expected_span_ids = HashSet::new();
    for export in 0..TRACE_EXPORTS {
        let spans = (0..SPANS_PER_EXPORT)
            .map(|index| {
                let span_id = span_id(export * SPANS_PER_EXPORT + index + 1);
                let span = span_with_payload(TRACE_ID, &span_id, "wanted");
                expected_span_ids.insert(span_id);
                span
            })
            .collect();
        ingestion.export(otlp::export_request(SERVICE, spans)).await;
    }
    let expected_span_ids = Arc::new(expected_span_ids);

    // Other traces keep arriving, so every snapshot ingestion writes is a
    // different file.
    let stop = Arc::new(AtomicBool::new(false));
    let writer = tokio::spawn({
        let ingestion = ingestion.clone();
        let stop = stop.clone();
        async move {
            let mut next: u64 = 1_000_000;
            while !stop.load(Ordering::Relaxed) {
                let trace_id = format!("{next:032x}");
                let spans = (0..100)
                    .map(|index| span_with_payload(&trace_id, &span_id(next + index), "other"))
                    .collect();
                next += 100;
                ingestion.export(otlp::export_request(SERVICE, spans)).await;
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        }
    });

    let deadline = Instant::now() + READING;
    let readers: Vec<_> = (0..READERS)
        .map(|_| {
            let state = app.state.clone();
            let expected_span_ids = expected_span_ids.clone();
            tokio::spawn(async move {
                let mut queries = 0;
                while Instant::now() < deadline {
                    let spans = repository::trace_spans(&state, TRACE_ID).await.unwrap();
                    assert_eq!(spans.len(), expected_span_ids.len());
                    let span_ids: HashSet<String> =
                        spans.into_iter().map(|span| span.span_id).collect();
                    assert_eq!(span_ids, *expected_span_ids);
                    queries += 1;
                }
                queries
            })
        })
        .collect();

    let mut queries = 0;
    for reader in readers {
        queries += reader.await.unwrap();
    }
    stop.store(true, Ordering::Relaxed);
    writer.await.unwrap();
    assert!(queries > 0);
}
