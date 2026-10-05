//! EXPERIMENT (2026-10-04): what concurrent queries see while ingestion
//! rewrites the one hot snapshot file they share.
//!
//! Ingestion writes the hot snapshot to one fixed path and replaces it by
//! rename whenever a request arrives after the reuse period. A query that was
//! handed the path earlier may still be reading it.

use std::collections::HashSet;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::time::{Duration, Instant};

use super::harness;
use super::otlp;

const SERVICE: &str = "svc-snapshot-sharing";
const TRACE_ID: &str = "a1b2c3d4e5f60718293a4b5c6d7e8f90";
const TRACE_SPANS: u64 = 2_000;

fn span_id(number: u64) -> String {
    format!("{number:016x}")
}

async fn run(snapshot_reuse: Duration, readers: usize, seconds: u64) -> (usize, usize, usize, usize) {
    let (app, ingestion) = harness::start_with_snapshot_reuse(snapshot_reuse).await;
    let ingestion = Arc::new(ingestion);
    let payload = "x".repeat(256);

    // The trace every reader asks for. It stays in the write-ahead log.
    let mut expected = HashSet::new();
    for export in 0..10 {
        let spans = (0..TRACE_SPANS / 10)
            .map(|index| {
                let id = span_id(export * (TRACE_SPANS / 10) + index + 1);
                expected.insert(id.clone());
                opentelemetry_proto::tonic::trace::v1::Span {
                    attributes: vec![otlp::text_attribute("payload", &payload)],
                    ..otlp::span(TRACE_ID, &id, "wanted")
                }
            })
            .collect();
        ingestion.export(otlp::export_request(SERVICE, spans)).await;
    }
    let expected = Arc::new(expected);

    let stop = Arc::new(AtomicBool::new(false));
    // Other traces keep arriving, so every rewritten snapshot is a different file.
    let writer = tokio::spawn({
        let ingestion = ingestion.clone();
        let stop = stop.clone();
        let payload = payload.clone();
        async move {
            let mut next: u64 = 1_000_000;
            while !stop.load(Ordering::Relaxed) {
                let trace = format!("{:032x}", next);
                let spans = (0..100)
                    .map(|index| opentelemetry_proto::tonic::trace::v1::Span {
                        attributes: vec![otlp::text_attribute("payload", &payload)],
                        ..otlp::span(&trace, &span_id(next + index), "other")
                    })
                    .collect();
                next += 100;
                ingestion.export(otlp::export_request(SERVICE, spans)).await;
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        }
    });

    let complete = Arc::new(AtomicUsize::new(0));
    let incomplete = Arc::new(AtomicUsize::new(0));
    let failed = Arc::new(AtomicUsize::new(0));
    let total = Arc::new(AtomicUsize::new(0));
    let deadline = Instant::now() + Duration::from_secs(seconds);
    let mut tasks = Vec::new();
    for _ in 0..readers {
        let state = app.state.clone();
        let expected = expected.clone();
        let (complete, incomplete, failed, total) =
            (complete.clone(), incomplete.clone(), failed.clone(), total.clone());
        tasks.push(tokio::spawn(async move {
            while Instant::now() < deadline {
                total.fetch_add(1, Ordering::Relaxed);
                let context = state.ingestion.query_context().await;
                let sources = crate::features::otel_spans::query::QuerySources {
                    cold_files: context.recent_cold_paths,
                    hot_snapshot: context.hot_snapshot_path,
                };
                match state.query.trace_spans(&sources, TRACE_ID).await {
                    Ok(spans) => {
                        let ids: HashSet<String> =
                            spans.iter().map(|span| span.span_id.clone()).collect();
                        if spans.len() == expected.len() && ids == *expected {
                            complete.fetch_add(1, Ordering::Relaxed);
                        } else {
                            incomplete.fetch_add(1, Ordering::Relaxed);
                            eprintln!("INCOMPLETE: {} spans, {} distinct", spans.len(), ids.len());
                        }
                    }
                    Err(error) => {
                        failed.fetch_add(1, Ordering::Relaxed);
                        let text = error.to_string();
                        eprintln!("FAILED: {}", &text[..text.len().min(220)]);
                    }
                }
            }
        }));
    }
    for task in tasks {
        task.await.unwrap();
    }
    stop.store(true, Ordering::Relaxed);
    writer.await.unwrap();
    (
        total.load(Ordering::Relaxed),
        complete.load(Ordering::Relaxed),
        incomplete.load(Ordering::Relaxed),
        failed.load(Ordering::Relaxed),
    )
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn experiment_concurrent_queries_with_the_deployment_reuse_period() {
    for (label, reuse, readers) in [
        ("reuse 1000 ms, 1 reader", Duration::from_millis(1000), 1),
        ("reuse 1000 ms, 8 readers", Duration::from_millis(1000), 8),
        ("reuse 0 ms, 8 readers", Duration::ZERO, 8),
    ] {
        let (total, complete, incomplete, failed) = run(reuse, readers, 8).await;
        eprintln!(
            "EXPERIMENT {label}: queries={total} complete={complete} incomplete={incomplete} failed={failed}"
        );
    }
}
