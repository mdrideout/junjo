//! The trace list's "has LLM spans" filter, over spans that follow the GenAI
//! semantic conventions.
//!
//! For indexed data the filter reads the metadata index, which records a
//! trace as an LLM trace when the indexer classifies one of its spans as an
//! LLM span. The xAI SDK emits GenAI spans (`gen_ai.provider.name` is `xai`),
//! so a trace with one must be listed.
//!
//! Before a file is indexed the filter classifies its spans itself: in the
//! hot snapshot while they are unflushed, and in the flushed file until the
//! indexer reaches it (ingestion ADR-002).

use axum::http::StatusCode;
use opentelemetry_proto::tonic::trace::v1::Span;
use opentelemetry_proto::tonic::trace::v1::span::SpanKind;
use serde_json::{Value, json};

use super::{harness, otlp};
use crate::app::router;
use crate::test_http::{get, post, send, sign_up};

const SERVICE: &str = "svc-genai-xai-has-llm";
const LLM_TRACE_ID: &str = "7c9e6679742540de944be07fc1f90ae7";
const LLM_ROOT_SPAN_ID: &str = "a3ce929d0e0e4731";
const LLM_SPAN_ID: &str = "a3ce929d0e0e4732";
/// A trace of the same service with no LLM span.
const PLAIN_TRACE_ID: &str = "1b9d6bcd0bbf4d4bb16e2b7a4a7e3c55";
const PLAIN_ROOT_SPAN_ID: &str = "a3ce929d0e0e4733";

/// The trace and span identifier of each listed span, in the listed order.
fn identities(body: &Value) -> Vec<(&str, &str)> {
    body.as_array()
        .unwrap()
        .iter()
        .map(|span| {
            (
                span["trace_id"].as_str().unwrap(),
                span["span_id"].as_str().unwrap(),
            )
        })
        .collect()
}

/// A trace with a GenAI span under its root, and a newer trace of the same
/// service with a root span only.
fn llm_trace_and_plain_trace() -> Vec<Span> {
    let llm_root = Span {
        kind: SpanKind::Server as i32,
        ..otlp::span(LLM_TRACE_ID, LLM_ROOT_SPAN_ID, "root-span")
    };
    let llm_span = Span {
        parent_span_id: otlp::hex_bytes(LLM_ROOT_SPAN_ID),
        start_time_unix_nano: otlp::START_NS + 10_000,
        end_time_unix_nano: otlp::START_NS + 1_010_000,
        attributes: vec![
            otlp::text_attribute("gen_ai.provider.name", "xai"),
            otlp::text_attribute("gen_ai.operation.name", "chat"),
            otlp::text_attribute("gen_ai.model.name", "grok-4-1-fast-non-reasoning"),
        ],
        ..otlp::span(LLM_TRACE_ID, LLM_SPAN_ID, "chat.sample")
    };
    // One second newer than the LLM trace.
    let plain_root = Span {
        kind: SpanKind::Server as i32,
        start_time_unix_nano: otlp::START_NS + 1_000_000_000,
        end_time_unix_nano: otlp::START_NS + 1_001_000_000,
        ..otlp::span(PLAIN_TRACE_ID, PLAIN_ROOT_SPAN_ID, "root-span")
    };
    vec![llm_root, llm_span, plain_root]
}

#[tokio::test]
async fn the_llm_filter_lists_the_root_of_an_indexed_trace_with_a_genai_span() {
    let (mut app, ingestion) = harness::start().await;
    let indexer = app.spawn_indexer();
    let router = router(app.state.clone(), false);
    let cookie = sign_up(&router).await;

    ingestion
        .export(otlp::export_request(SERVICE, llm_trace_and_plain_trace()))
        .await;

    // The operator's flush makes the spans cold and indexes the new file.
    let flushed = send(
        &router,
        post("/api/v1/admin/flush-wal", Some(&cookie), json!({})),
    )
    .await;
    assert_eq!(flushed.status, StatusCode::OK, "{}", flushed.body);
    assert_eq!(flushed.body["files_indexed"], 1);

    // Both traces have a root span. Only one has an LLM span.
    let root_spans = format!("/api/v1/observability/services/{SERVICE}/spans/root");
    let all = send(
        &router,
        get(&format!("{root_spans}?limit=50"), Some(&cookie)),
    )
    .await;
    assert_eq!(all.status, StatusCode::OK, "{}", all.body);
    assert_eq!(
        identities(&all.body),
        [
            (PLAIN_TRACE_ID, PLAIN_ROOT_SPAN_ID),
            (LLM_TRACE_ID, LLM_ROOT_SPAN_ID),
        ]
    );

    let with_llm = send(
        &router,
        get(
            &format!("{root_spans}?has_llm=true&limit=50"),
            Some(&cookie),
        ),
    )
    .await;
    assert_eq!(with_llm.status, StatusCode::OK, "{}", with_llm.body);
    assert_eq!(
        identities(&with_llm.body),
        [(LLM_TRACE_ID, LLM_ROOT_SPAN_ID)]
    );

    (indexer.shutdown_sender())();
    indexer.finished.await.unwrap();
}

/// No indexer runs here, so the index never learns of the trace. The filter
/// must find its GenAI span in the hot snapshot, and after the flush in the
/// cold file that only ingestion's recent list names.
#[tokio::test]
async fn the_llm_filter_lists_a_trace_before_and_after_its_flush_without_the_index() {
    let (app, ingestion) = harness::start().await;
    let router = router(app.state.clone(), false);
    let cookie = sign_up(&router).await;
    let with_llm = format!("/api/v1/observability/services/{SERVICE}/spans/root?has_llm=true");

    ingestion
        .export(otlp::export_request(SERVICE, llm_trace_and_plain_trace()))
        .await;

    let unflushed = send(&router, get(&with_llm, Some(&cookie))).await;
    assert_eq!(unflushed.status, StatusCode::OK, "{}", unflushed.body);
    assert_eq!(
        identities(&unflushed.body),
        [(LLM_TRACE_ID, LLM_ROOT_SPAN_ID)]
    );

    assert_eq!(app.state.ingestion.flush_wal().await, Ok(()));
    let context = app.state.ingestion.query_context().await;
    assert_eq!(context.hot_snapshot_path, None);
    assert_eq!(context.recent_cold_paths.len(), 1);

    let flushed = send(&router, get(&with_llm, Some(&cookie))).await;
    assert_eq!(flushed.status, StatusCode::OK, "{}", flushed.body);
    assert_eq!(
        identities(&flushed.body),
        [(LLM_TRACE_ID, LLM_ROOT_SPAN_ID)]
    );
}
