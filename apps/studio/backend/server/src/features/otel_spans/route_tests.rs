//! The raw span routes through the router.

use axum::http::StatusCode;
use serde_json::{Value, json};

use crate::test_http::{app, get, send, sign_up};
use crate::test_support::TestSpan;

const SECOND: i64 = 1_000_000_000;

fn span_ids(body: &Value) -> Vec<&str> {
    body.as_array()
        .unwrap()
        .iter()
        .map(|span| span["span_id"].as_str().unwrap())
        .collect()
}

/// A span that starts `second` seconds into the test's timeline.
fn span_at(trace_id: &str, span_id: &str, service_name: &str, second: i64) -> TestSpan {
    TestSpan::new(trace_id, span_id, service_name).times(second * SECOND, (second + 1) * SECOND)
}

#[tokio::test]
async fn services_come_from_the_metadata_index_when_ingestion_is_unreachable() {
    let (router, mut app) = app();
    let cookie = sign_up(&router).await;
    app.index_cold_file(
        "a.parquet",
        &[
            TestSpan::new("trace-1", "span-1", "checkout"),
            TestSpan::new("trace-2", "span-2", "billing"),
        ],
    );

    let reply = send(
        &router,
        get("/api/v1/observability/services", Some(&cookie)),
    )
    .await;

    assert_eq!(reply.status, StatusCode::OK);
    assert_eq!(reply.body, json!(["billing", "checkout"]));
}

#[tokio::test]
async fn trace_spans_are_read_from_indexed_cold_files() {
    let (router, mut app) = app();
    let cookie = sign_up(&router).await;
    app.index_cold_file(
        "a.parquet",
        &[
            TestSpan::new("trace-1", "span-1", "checkout")
                .attributes(r#"{"junjo.span_type":"workflow"}"#),
            TestSpan::new("trace-2", "span-2", "checkout"),
        ],
    );
    app.index_cold_file(
        "b.parquet",
        &[TestSpan::new("trace-1", "span-3", "billing")],
    );

    let reply = send(
        &router,
        get("/api/v1/observability/traces/trace-1/spans", Some(&cookie)),
    )
    .await;

    assert_eq!(reply.status, StatusCode::OK);
    let mut ids = span_ids(&reply.body);
    ids.sort();
    assert_eq!(ids, ["span-1", "span-3"]);
    let workflow = reply
        .body
        .as_array()
        .unwrap()
        .iter()
        .find(|span| span["span_id"] == "span-1")
        .unwrap();
    assert_eq!(
        workflow["attributes_json"],
        json!({"junjo.span_type": "workflow"})
    );
    assert_eq!(workflow["events_json"], json!([]));
    assert_eq!(workflow["parent_span_id"], Value::Null);
    assert_eq!(workflow["kind"], "INTERNAL");

    let unknown = send(
        &router,
        get("/api/v1/observability/traces/missing/spans", Some(&cookie)),
    )
    .await;
    assert_eq!(unknown.status, StatusCode::OK);
    assert_eq!(unknown.body, json!([]));
}

#[tokio::test]
async fn one_span_is_returned_or_null() {
    let (router, mut app) = app();
    let cookie = sign_up(&router).await;
    app.index_cold_file(
        "a.parquet",
        &[
            TestSpan::new("trace-1", "span-1", "checkout").name("first"),
            TestSpan::new("trace-1", "span-2", "checkout").name("second"),
        ],
    );

    let found = send(
        &router,
        get(
            "/api/v1/observability/traces/trace-1/spans/span-2",
            Some(&cookie),
        ),
    )
    .await;
    assert_eq!(found.status, StatusCode::OK);
    assert_eq!(found.body["span_id"], "span-2");
    assert_eq!(found.body["name"], "second");

    // A span the trace does not have is a null body, not an error.
    for uri in [
        "/api/v1/observability/traces/trace-1/spans/span-9",
        "/api/v1/observability/traces/trace-9/spans/span-1",
    ] {
        let missing = send(&router, get(uri, Some(&cookie))).await;
        assert_eq!(missing.status, StatusCode::OK, "{uri}");
        assert_eq!(missing.body, Value::Null, "{uri}");
    }
}

#[tokio::test]
async fn service_listings_are_newest_first_and_limited() {
    let (router, mut app) = app();
    let cookie = sign_up(&router).await;
    app.index_cold_file(
        "a.parquet",
        &[
            span_at("trace-1", "root-1", "checkout", 10),
            span_at("trace-1", "child-1", "checkout", 11).parent("root-1"),
            span_at("trace-2", "root-2", "checkout", 20)
                .attributes(r#"{"junjo.span_type":"workflow"}"#),
            span_at("trace-2", "llm-2", "checkout", 21)
                .parent("root-2")
                .attributes(r#"{"gen_ai.operation.name":"chat"}"#),
            span_at("trace-3", "root-3", "billing", 30),
        ],
    );
    let listing = async |path: &str| {
        let reply = send(
            &router,
            get(
                &format!("/api/v1/observability/services/checkout/{path}"),
                Some(&cookie),
            ),
        )
        .await;
        assert_eq!(reply.status, StatusCode::OK, "{path}: {}", reply.body);
        reply.body
    };

    assert_eq!(
        span_ids(&listing("spans").await),
        ["llm-2", "root-2", "child-1", "root-1"]
    );
    assert_eq!(
        span_ids(&listing("spans?limit=2").await),
        ["llm-2", "root-2"]
    );
    assert_eq!(span_ids(&listing("spans/root").await), ["root-2", "root-1"]);
    assert_eq!(
        span_ids(&listing("spans/root?has_llm=false&limit=1").await),
        ["root-2"]
    );
    // Only the trace that contains an LLM span.
    assert_eq!(
        span_ids(&listing("spans/root?has_llm=true").await),
        ["root-2"]
    );
    assert_eq!(span_ids(&listing("workflows").await), ["root-2"]);
}

#[tokio::test]
async fn a_listing_limit_is_1_to_250() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;
    for path in ["spans", "spans/root", "workflows"] {
        for (query, expected) in [
            ("", StatusCode::OK),
            ("?limit=1", StatusCode::OK),
            ("?limit=250", StatusCode::OK),
            ("?limit=0", StatusCode::UNPROCESSABLE_ENTITY),
            ("?limit=251", StatusCode::UNPROCESSABLE_ENTITY),
            ("?limit=many", StatusCode::UNPROCESSABLE_ENTITY),
        ] {
            let uri = format!("/api/v1/observability/services/checkout/{path}{query}");
            let reply = send(&router, get(&uri, Some(&cookie))).await;
            assert_eq!(reply.status, expected, "{uri}");
            if expected == StatusCode::OK {
                assert_eq!(reply.body, json!([]), "{uri}");
            } else {
                assert_eq!(reply.body["code"], "invalid_request", "{uri}");
            }
        }
    }
    let not_a_flag = send(
        &router,
        get(
            "/api/v1/observability/services/checkout/spans/root?has_llm=perhaps",
            Some(&cookie),
        ),
    )
    .await;
    assert_eq!(not_a_flag.status, StatusCode::UNPROCESSABLE_ENTITY);
}

#[tokio::test]
async fn a_service_name_is_one_percent_encoded_path_segment() {
    let (router, mut app) = app();
    let cookie = sign_up(&router).await;
    app.index_cold_file(
        "a.parquet",
        &[
            span_at("trace-1", "root-1", "team/checkout api", 10),
            span_at("trace-2", "root-2", "team", 20),
        ],
    );

    for path in ["spans", "spans/root"] {
        let reply = send(
            &router,
            get(
                &format!("/api/v1/observability/services/team%2Fcheckout%20api/{path}"),
                Some(&cookie),
            ),
        )
        .await;
        assert_eq!(reply.status, StatusCode::OK, "{path}");
        assert_eq!(span_ids(&reply.body), ["root-1"], "{path}");
    }
}
