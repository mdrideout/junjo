use axum::http::StatusCode;
use junjo_evidence::agent_diagnostics::assembler::assemble_agent_summary;
use junjo_evidence::trace_evidence::assembler::percent_encode;
use serde_json::{Value, json};

use crate::test_http::{app, get, send, sign_up};
use crate::test_support::{TestSpan, telemetry_fixtures};

/// Every Agent fixture, consumer and producer.
fn agent_fixtures() -> Vec<(String, Value)> {
    ["consumer", "producer"]
        .iter()
        .flat_map(|directory| telemetry_fixtures(&format!("agent/{directory}")))
        .collect()
}

fn is_agent(span: &Value) -> bool {
    span["attributes_json"]["junjo.span_type"] == "agent"
}

/// The summaries a listing of the fixture's service must return: one per
/// Agent owner span, newest first, and by trace and span identifier among
/// executions that started together.
fn expected_summaries(fixture: &Value) -> Vec<Value> {
    let mut summaries: Vec<_> = fixture["spans"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|span| is_agent(span))
        .map(|span| assemble_agent_summary(span.as_object().unwrap()).unwrap())
        .collect();
    summaries.sort_by(|left, right| {
        (right.start_time, &left.trace_id, &left.agent_span_id).cmp(&(
            left.start_time,
            &right.trace_id,
            &right.agent_span_id,
        ))
    });
    summaries
        .iter()
        .map(|summary| serde_json::to_value(summary).unwrap())
        .collect()
}

fn listing(fixture: &Value, filters: &str) -> String {
    let resource = &fixture["spans"][0]["resource_attributes_json"];
    format!(
        "/api/v1/agent-executions?service_namespace={}&service_name={}{filters}",
        resource["service.namespace"].as_str().unwrap_or(""),
        fixture["service_name"].as_str().unwrap(),
    )
}

#[tokio::test]
async fn stored_agent_spans_are_listed_as_their_summaries() {
    let (router, mut app) = app();
    let cookie = sign_up(&router).await;
    let fixtures = agent_fixtures();
    for (name, fixture) in &fixtures {
        let spans: Vec<TestSpan> = fixture["spans"]
            .as_array()
            .unwrap()
            .iter()
            .map(TestSpan::from_api_span)
            .collect();
        app.index_cold_file(&format!("{name}.parquet"), &spans);
    }

    let mut listed_executions = 0;
    for (name, fixture) in &fixtures {
        let expected = expected_summaries(fixture);
        let reply = send(&router, get(&listing(fixture, ""), Some(&cookie))).await;
        assert_eq!(reply.status, StatusCode::OK, "{name}: {}", reply.body);
        assert_eq!(reply.body, Value::Array(expected.clone()), "{name}");
        listed_executions += expected.len();

        let limited = send(&router, get(&listing(fixture, "&limit=1"), Some(&cookie))).await;
        assert_eq!(limited.body, json!(expected[..1]), "{name}");
    }
    assert!(listed_executions >= fixtures.len());
}

#[tokio::test]
async fn filters_use_exact_values_and_inclusive_time_bounds() {
    let (router, mut app) = app();
    let cookie = sign_up(&router).await;
    let (_, fixture) = agent_fixtures().remove(0);
    let spans: Vec<TestSpan> = fixture["spans"]
        .as_array()
        .unwrap()
        .iter()
        .map(TestSpan::from_api_span)
        .collect();
    app.index_cold_file("agent.parquet", &spans);
    let expected = expected_summaries(&fixture);
    let summary = &expected[0];
    let text = |name: &str| summary[name].as_str().unwrap();

    let count = async |filters: String| {
        let reply = send(&router, get(&listing(&fixture, &filters), Some(&cookie))).await;
        assert_eq!(reply.status, StatusCode::OK, "{filters}: {}", reply.body);
        reply.body.as_array().unwrap().len()
    };
    let matching = expected
        .iter()
        .filter(|other| other["agent_key"] == summary["agent_key"])
        .count();
    assert_eq!(
        count(format!("&agent_key={}", text("agent_key"))).await,
        matching
    );
    assert_eq!(count("&agent_key=another-agent".to_string()).await, 0);
    assert_eq!(
        count(format!("&structural_id={}", text("structural_id"))).await,
        expected
            .iter()
            .filter(|other| other["structural_id"] == summary["structural_id"])
            .count()
    );
    assert_eq!(
        count(format!("&outcome={}", text("outcome"))).await,
        expected
            .iter()
            .filter(|other| other["outcome"] == summary["outcome"])
            .count()
    );
    assert_eq!(
        count("&service_version=no-such-version".to_string()).await,
        0
    );

    // The bounds are inclusive at the execution's own instants.
    let bounds = format!(
        "&start_time={}&end_time={}",
        text("start_time").replace('+', "%2B"),
        text("end_time").replace('+', "%2B")
    );
    assert!(count(bounds).await >= 1);
    assert_eq!(
        count("&start_time=2999-01-01T00:00:00Z".to_string()).await,
        0
    );
    assert_eq!(count("&end_time=2000-01-01T00:00:00Z".to_string()).await, 0);

    // Another namespace is another service.
    let other_namespace = send(
        &router,
        get(
            &format!(
                "/api/v1/agent-executions?service_namespace=another&service_name={}",
                fixture["service_name"].as_str().unwrap()
            ),
            Some(&cookie),
        ),
    )
    .await;
    assert_eq!(other_namespace.body, json!([]));
}

/// The first Agent fixture and its Agent owner span.
fn fixture_and_owner() -> (Value, Value) {
    let (_, fixture) = agent_fixtures().remove(0);
    let spans = fixture["spans"].as_array().unwrap();
    let owner = spans.iter().find(|span| is_agent(span)).unwrap().clone();
    (fixture, owner)
}

#[tokio::test]
async fn a_listing_walks_past_the_newer_executions_of_another_namespace() {
    let (router, mut app) = app();
    let cookie = sign_up(&router).await;
    let (fixture, owner) = fixture_and_owner();
    // Five newer executions of the same service name in another namespace,
    // one to a file, and then the fixture's own.
    for copy in 0..5 {
        let mut newer = owner.clone();
        newer["span_id"] = json!(format!("{copy:016x}"));
        newer["start_time"] = json!(format!("2026-07-14T12:00:0{copy}.000000+00:00"));
        newer["end_time"] = json!(format!("2026-07-14T12:00:0{copy}.000500+00:00"));
        newer["resource_attributes_json"]["service.namespace"] = json!("another");
        app.index_cold_file(
            &format!("newer-{copy}.parquet"),
            &[TestSpan::from_api_span(&newer)],
        );
    }
    app.index_cold_file("owner.parquet", &[TestSpan::from_api_span(&owner)]);

    // A page of one: the listing takes six pages to reach the execution.
    let reply = send(&router, get(&listing(&fixture, "&limit=1"), Some(&cookie))).await;

    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    let listed = reply.body.as_array().unwrap();
    assert_eq!(listed.len(), 1);
    assert_eq!(listed[0]["agent_span_id"], owner["span_id"]);
}

#[tokio::test]
async fn a_filter_value_is_matched_as_the_text_ingestion_stores() {
    let (router, mut app) = app();
    let cookie = sign_up(&router).await;
    let (fixture, owner) = fixture_and_owner();
    // A key with characters JSON escapes, a non-ASCII letter, and the two
    // characters a pattern would read as wildcards.
    let key = "caf\u{e9} \"50%_off\" \\ agent";
    let mut wanted = owner.clone();
    wanted["span_id"] = json!("00000000000000aa");
    wanted["attributes_json"]["junjo.agent.key"] = json!(key);
    let mut near = owner.clone();
    near["span_id"] = json!("00000000000000bb");
    near["attributes_json"]["junjo.agent.key"] = json!("caf\u{e9} \"50x-off\" \\ agent");
    app.index_cold_file(
        "agent.parquet",
        &[
            TestSpan::from_api_span(&owner),
            TestSpan::from_api_span(&wanted),
            TestSpan::from_api_span(&near),
        ],
    );

    let filters = format!("&agent_key={}", percent_encode(key));
    let reply = send(&router, get(&listing(&fixture, &filters), Some(&cookie))).await;

    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    let listed = reply.body.as_array().unwrap();
    assert_eq!(listed.len(), 1, "{}", reply.body);
    assert_eq!(listed[0]["agent_span_id"], "00000000000000aa");
    assert_eq!(listed[0]["agent_key"], key);
}

#[tokio::test]
async fn a_time_bound_keeps_an_execution_whose_stored_time_has_finer_digits() {
    let (router, mut app) = app();
    let cookie = sign_up(&router).await;
    let (fixture, mut owner) = fixture_and_owner();
    // A summary's times are whole microseconds. The stored span ends 999
    // nanoseconds into its microsecond.
    owner["end_time"] = json!("2026-07-13T12:00:00.000500999+00:00");
    app.index_cold_file("owner.parquet", &[TestSpan::from_api_span(&owner)]);

    let count = async |filters: &str| {
        let reply = send(&router, get(&listing(&fixture, filters), Some(&cookie))).await;
        assert_eq!(reply.status, StatusCode::OK, "{filters}: {}", reply.body);
        reply.body.as_array().unwrap().len()
    };

    assert_eq!(count("&end_time=2026-07-13T12:00:00.000500Z").await, 1);
    assert_eq!(count("&end_time=2026-07-13T12:00:00.000499Z").await, 0);
    assert_eq!(count("&start_time=2026-07-13T12:00:00Z").await, 1);
    assert_eq!(count("&start_time=2026-07-13T12:00:00.000001Z").await, 0);
}

#[tokio::test]
async fn evidence_that_cannot_be_read_fails_a_listing_only_when_the_walk_reaches_it() {
    let (router, mut app) = app();
    let cookie = sign_up(&router).await;
    let (fixture, owner) = fixture_and_owner();
    // An older Agent span that claims a contract Studio does not read.
    let mut unreadable = owner.clone();
    unreadable["span_id"] = json!("00000000000000aa");
    unreadable["start_time"] = json!("2026-07-12T12:00:00.000000+00:00");
    unreadable["end_time"] = json!("2026-07-12T12:00:00.000500+00:00");
    unreadable["attributes_json"]["junjo.telemetry.contract_version"] = json!(1);
    app.index_cold_file(
        "agent.parquet",
        &[
            TestSpan::from_api_span(&owner),
            TestSpan::from_api_span(&unreadable),
        ],
    );

    let newest = send(&router, get(&listing(&fixture, "&limit=1"), Some(&cookie))).await;
    assert_eq!(newest.status, StatusCode::OK, "{}", newest.body);
    assert_eq!(newest.body[0]["agent_span_id"], owner["span_id"]);

    let both = send(&router, get(&listing(&fixture, "&limit=2"), Some(&cookie))).await;
    assert_eq!(both.status, StatusCode::CONFLICT, "{}", both.body);
}

#[tokio::test]
async fn evidence_that_is_not_an_agent_execution_is_a_conflict() {
    let (router, mut app) = app();
    let cookie = sign_up(&router).await;
    let (_, fixture) = agent_fixtures().remove(0);
    let spans: Vec<TestSpan> = fixture["spans"]
        .as_array()
        .unwrap()
        .iter()
        .map(|span| {
            let mut span = span.clone();
            if is_agent(&span) {
                // An Agent span that claims a contract Studio does not read.
                span["attributes_json"]["junjo.telemetry.contract_version"] = json!(1);
            }
            TestSpan::from_api_span(&span)
        })
        .collect();
    app.index_cold_file("agent.parquet", &spans);

    let reply = send(&router, get(&listing(&fixture, ""), Some(&cookie))).await;
    assert_eq!(reply.status, StatusCode::CONFLICT, "{}", reply.body);
    assert_eq!(
        reply.body.as_object().unwrap().keys().collect::<Vec<_>>(),
        ["code", "message", "diagnostics"]
    );
    assert_eq!(reply.body["code"], "unsupported_contract");
    assert!(reply.body["diagnostics"].is_array());
}

#[tokio::test]
async fn the_listing_needs_a_session_and_an_explicit_service() {
    let (router, _app) = app();
    let listing = "/api/v1/agent-executions?service_namespace=&service_name=example";
    let anonymous = send(&router, get(listing, None)).await;
    assert_eq!(anonymous.status, StatusCode::UNAUTHORIZED);

    let cookie = sign_up(&router).await;
    let empty = send(&router, get(listing, Some(&cookie))).await;
    assert_eq!(empty.status, StatusCode::OK);
    assert_eq!(empty.body, json!([]));

    for query in [
        // The namespace must be stated, even when it is empty.
        "service_name=example",
        "service_namespace=&service_name=",
        "service_namespace=&service_name=example&agent_key=",
        "service_namespace=&service_name=example&outcome=unknown",
        "service_namespace=&service_name=example&limit=0",
        "service_namespace=&service_name=example&limit=251",
        "service_namespace=&service_name=example&unknown=1",
        // A time without an offset names no instant.
        "service_namespace=&service_name=example&start_time=2026-07-14T12:00:00",
        "service_namespace=&service_name=example&start_time=2026-07-14T12:00:01Z\
         &end_time=2026-07-14T12:00:00Z",
    ] {
        let reply = send(
            &router,
            get(&format!("/api/v1/agent-executions?{query}"), Some(&cookie)),
        )
        .await;
        assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY, "{query}");
        assert_eq!(reply.body["code"], "invalid_request", "{query}");
    }
}
