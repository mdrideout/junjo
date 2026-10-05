//! Ingestion stores the identifier of the API key that sent a span, and a
//! listing can ask for one key's spans.
//!
//! The identifier comes from this backend's key check, travels through
//! ingestion's validation cache, and is written with every span. The key
//! value itself is never stored.

use axum::http::StatusCode;

use super::{harness, otlp};
use crate::app::router;
use crate::test_http::{get, send, sign_up};

const SERVICE: &str = "svc-api-key-filter";
const TRACE_ID: &str = "5f0c2a1e9b7d4c3a8e6f1d2b3c4a5e6f";
const SPAN_ID: &str = "b1c2d3e4f5a60718";

#[tokio::test]
async fn a_span_is_listed_for_the_key_that_sent_it_before_and_after_its_flush() {
    let (app, ingestion) = harness::start().await;
    let router = router(app.state.clone(), false);
    let cookie = sign_up(&router).await;
    let listing = format!("/api/v1/observability/services/{SERVICE}/spans/root");
    let listed = |api_key_id: &'static str| {
        let router = router.clone();
        let uri = format!("{listing}?api_key_id={api_key_id}");
        let cookie = cookie.clone();
        async move {
            let reply = send(&router, get(&uri, Some(&cookie))).await;
            assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
            reply.body.as_array().unwrap().len()
        }
    };

    let span = otlp::span(TRACE_ID, SPAN_ID, "root-span");
    ingestion
        .export(otlp::export_request(SERVICE, vec![span]))
        .await;

    // The harness sends with the key whose identifier is `key-1`.
    assert_eq!(listed("key-1").await, 1);
    assert_eq!(listed("key-2").await, 0);

    assert_eq!(app.state.ingestion.flush_wal().await, Ok(()));
    assert_eq!(listed("key-1").await, 1);
    assert_eq!(listed("key-2").await, 0);
}
