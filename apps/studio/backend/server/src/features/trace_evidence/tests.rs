use axum::Router;
use axum::http::{Method, StatusCode};
use junjo_evidence::trace_evidence::assembler::{
    assemble_attempt_evidence_manifest, assemble_trace_evidence, select_attempt_span_evidence,
};
use junjo_evidence::trace_evidence::schemas::{NormalizedSpanEvidence, TraceEvidence};
use serde_json::{Value, json};

use crate::test_http::{Reply, app, get, post, request, send, sign_up};
use crate::test_support::{TestApp, TestSpan, telemetry_fixtures};

/// One shared Agent fixture by name.
fn fixture(name: &str) -> Value {
    telemetry_fixtures("agent/producer")
        .into_iter()
        .find(|(fixture_name, _)| fixture_name == name)
        .unwrap_or_else(|| panic!("no fixture named {name}"))
        .1
}

fn stored(fixture: &Value) -> Vec<TestSpan> {
    fixture["spans"]
        .as_array()
        .unwrap()
        .iter()
        .map(TestSpan::from_api_span)
        .collect()
}

#[tokio::test]
async fn a_stored_trace_is_returned_as_one_cohesive_document() {
    let (router, mut app) = app();
    let cookie = sign_up(&router).await;
    let fixture = fixture("tool_invokes_nested_workflow");
    let trace_id = fixture["trace_id"].as_str().unwrap();
    app.index_cold_file("trace.parquet", &stored(&fixture));

    let reply = send(
        &router,
        get(&format!("/api/v1/trace-evidence/{trace_id}"), Some(&cookie)),
    )
    .await;
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    assert_eq!(reply.body["trace_id"], trace_id);
    assert_eq!(
        reply.body["spans"].as_array().unwrap().len(),
        fixture["spans"].as_array().unwrap().len()
    );
    assert!(
        !reply.body["executables_by_span_id"]
            .as_object()
            .unwrap()
            .is_empty()
    );

    // The document is exactly the evidence of the spans the raw span API
    // returns for the trace.
    let raw = send(
        &router,
        get(
            &format!("/api/v1/observability/traces/{trace_id}/spans"),
            Some(&cookie),
        ),
    )
    .await;
    let spans: Vec<NormalizedSpanEvidence> = serde_json::from_value(raw.body).unwrap();
    let expected = assemble_trace_evidence(trace_id, spans);
    assert_eq!(reply.body, serde_json::to_value(&expected).unwrap());
}

#[tokio::test]
async fn a_trace_with_no_stored_span_is_not_found() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;
    let uri = format!("/api/v1/trace-evidence/{}", "a".repeat(32));

    let anonymous = send(&router, get(&uri, None)).await;
    assert_eq!(anonymous.status, StatusCode::UNAUTHORIZED);

    let missing = send(&router, get(&uri, Some(&cookie))).await;
    assert_eq!(missing.status, StatusCode::NOT_FOUND);
    assert_eq!(
        missing.body,
        json!({"code": "not_found", "message": "Trace not found"})
    );

    for trace_id in ["A".repeat(32), "a".repeat(31), "not-a-trace".to_string()] {
        let reply = send(
            &router,
            get(&format!("/api/v1/trace-evidence/{trace_id}"), Some(&cookie)),
        )
        .await;
        assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY, "{trace_id}");
    }
}

const DATASETS: &str = "/api/v1/evaluation/datasets";
const RUNS: &str = "/api/v1/evaluation/runs";
const ATTEMPTS: &str = "/api/v1/evaluation/attempts";
const ATTEMPT_EVIDENCE: &str = "/api/v1/trace-evidence/attempts";
const NOT_STORED_SPAN_ID: &str = "ffffffffffffffff";

/// One fresh application, its signed-in first user, and one queued Attempt.
struct Evaluation {
    router: Router,
    cookie: String,
    app: TestApp,
    attempt_id: String,
}

impl Evaluation {
    /// A dataset with one case, locked and run once.
    async fn new() -> Self {
        let (router, app) = app();
        let cookie = sign_up(&router).await;
        let send_ok = async |request| {
            let reply = send(&router, request).await;
            assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
            reply.body
        };
        let dataset = send_ok(post(
            DATASETS,
            Some(&cookie),
            json!({"application_key": "ai_chat", "key": "evidence", "name": "Evidence"}),
        ))
        .await;
        let dataset_id = dataset["id"].as_str().unwrap();
        send_ok(post(
            &format!("{DATASETS}/{dataset_id}/cases"),
            Some(&cookie),
            json!({
                "case_key": "case_1",
                "evaluation_name": "Evidence",
                "origin": "authored",
                "target_kind": "agent",
                "target_key": "agent",
                "target_name": "Agent",
                "input_version": 1,
                "input_json": {"prompt": "hello"},
                "evaluator_key": "quality",
                "evaluator_version": 1,
            }),
        ))
        .await;
        send_ok(request(
            Method::PUT,
            &format!("{DATASETS}/{dataset_id}/lock"),
            Some(&cookie),
            None,
        ))
        .await;
        let run = send_ok(post(
            RUNS,
            Some(&cookie),
            json!({
                "dataset_id": dataset_id,
                "request_key": "run-1",
                "run_label": "baseline",
                "source_revision": "a".repeat(40),
            }),
        ))
        .await;
        let attempt_id = run["cases"][0]["attempt"]["id"]
            .as_str()
            .unwrap()
            .to_string();
        Self {
            router,
            cookie,
            app,
            attempt_id,
        }
    }

    /// Store a fixture's spans as an indexed cold file.
    fn store(&mut self, fixture: &Value) {
        self.app.index_cold_file("trace.parquet", &stored(fixture));
    }

    /// Bind the Attempt to the execution `evidence` names.
    async fn bind(&self, evidence: &Value) {
        let reply = send(
            &self.router,
            request(
                Method::PUT,
                &format!("{ATTEMPTS}/{}/evidence", self.attempt_id),
                Some(&self.cookie),
                Some(json!({"evidence": evidence})),
            ),
        )
        .await;
        assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    }

    async fn manifest(&self) -> Reply {
        send(
            &self.router,
            get(
                &format!("{ATTEMPT_EVIDENCE}/{}/manifest", self.attempt_id),
                Some(&self.cookie),
            ),
        )
        .await
    }

    async fn spans(&self, body: Value) -> Reply {
        send(
            &self.router,
            post(
                &format!("{ATTEMPT_EVIDENCE}/{}/spans", self.attempt_id),
                Some(&self.cookie),
                body,
            ),
        )
        .await
    }

    /// The evidence of one stored trace, assembled from the spans the raw
    /// span API returns for it.
    async fn evidence(&self, trace_id: &str) -> TraceEvidence {
        let raw = send(
            &self.router,
            get(
                &format!("/api/v1/observability/traces/{trace_id}/spans"),
                Some(&self.cookie),
            ),
        )
        .await;
        assemble_trace_evidence(trace_id, serde_json::from_value(raw.body).unwrap())
    }
}

/// A reference to one fixture span as a span of any OpenTelemetry producer.
fn span_reference(span: &Value) -> Value {
    let resource = &span["resource_attributes_json"];
    json!({
        "kind": "otel_span",
        "service_namespace": resource["service.namespace"].as_str().unwrap_or(""),
        "service_name": resource["service.name"],
        "trace_id": span["trace_id"],
        "span_id": span["span_id"],
    })
}

/// A reference to the Junjo execution one fixture owner span records.
fn execution_reference(owner: &Value) -> Value {
    let resource = &owner["resource_attributes_json"];
    json!({
        "kind": "junjo_execution",
        "service_namespace": resource["service.namespace"].as_str().unwrap_or(""),
        "service_name": resource["service.name"],
        "executable_type": owner["attributes_json"]["junjo.span_type"],
        "runtime_id": owner["attributes_json"]["junjo.executable_runtime_id"],
    })
}

fn assert_no_attempt_evidence(reply: &Reply) {
    assert_eq!(reply.status, StatusCode::NOT_FOUND, "{}", reply.body);
    assert_eq!(
        reply.body,
        json!({"code": "not_found", "message": "Attempt evidence not found"})
    );
}

#[tokio::test]
async fn an_attempt_bound_to_a_span_gets_a_manifest_and_selected_spans() {
    let mut evaluation = Evaluation::new().await;
    let fixture = fixture("multi_tool_first_failure");
    let subject_span = &fixture["spans"][0];
    let (trace_id, span_id) = (
        subject_span["trace_id"].as_str().unwrap(),
        subject_span["span_id"].as_str().unwrap(),
    );
    let service_name = fixture["service_name"].as_str().unwrap();
    evaluation.store(&fixture);
    let reference = span_reference(subject_span);
    evaluation.bind(&reference).await;

    // An exact span has one page: its place in its trace.
    let path = format!("/traces/{service_name}/{trace_id}/{span_id}");
    let subject = json!({
        "attempt_id": evaluation.attempt_id,
        "reference": reference,
        "trace_id": trace_id,
        "span_id": span_id,
        "detail_path": path,
        "failure_path": path,
        "trace_path": path,
    });
    let evidence = evaluation.evidence(trace_id).await;

    let manifest = evaluation.manifest().await;
    assert_eq!(manifest.status, StatusCode::OK, "{}", manifest.body);
    let mut expected =
        serde_json::to_value(assemble_attempt_evidence_manifest(service_name, &evidence)).unwrap();
    expected["subject"] = subject.clone();
    assert_eq!(manifest.body, expected);
    assert_eq!(
        manifest.body.as_object().unwrap().keys().next().unwrap(),
        "subject"
    );
    assert_eq!(
        manifest.body["trace"]["span_count"],
        fixture["spans"].as_array().unwrap().len()
    );
    assert!(!manifest.body["failures"].as_array().unwrap().is_empty());

    // Selected spans come back in the order asked for, and a span the trace
    // does not have is named, not ignored.
    let selected = evaluation
        .spans(json!({"span_ids": [NOT_STORED_SPAN_ID, span_id]}))
        .await;
    assert_eq!(selected.status, StatusCode::OK, "{}", selected.body);
    let chosen = select_attempt_span_evidence(
        &evidence,
        &[NOT_STORED_SPAN_ID.to_string(), span_id.to_string()],
    );
    assert_eq!(
        selected.body,
        json!({
            "subject": subject,
            "items": serde_json::to_value(&chosen.items).unwrap(),
            "missing_span_ids": [NOT_STORED_SPAN_ID],
        })
    );
    assert_eq!(selected.body["items"].as_array().unwrap().len(), 1);
    assert_eq!(selected.body["items"][0]["span"]["span_id"], span_id);
}

#[tokio::test]
async fn an_attempt_bound_to_an_execution_is_resolved_to_its_owner_span() {
    let mut evaluation = Evaluation::new().await;
    let fixture = fixture("multi_tool_first_failure");
    let owner = fixture["spans"]
        .as_array()
        .unwrap()
        .iter()
        .find(|span| span["attributes_json"]["junjo.span_type"] == "agent")
        .unwrap();
    let (trace_id, span_id) = (
        owner["trace_id"].as_str().unwrap(),
        owner["span_id"].as_str().unwrap(),
    );
    evaluation.store(&fixture);
    let reference = execution_reference(owner);
    evaluation.bind(&reference).await;

    let manifest = evaluation.manifest().await;
    assert_eq!(manifest.status, StatusCode::OK, "{}", manifest.body);
    assert_eq!(
        manifest.body["subject"],
        json!({
            "attempt_id": evaluation.attempt_id,
            "reference": reference,
            "trace_id": trace_id,
            "span_id": span_id,
            "detail_path": format!("/agents/{trace_id}/{span_id}"),
            "failure_path": format!("/agents/{trace_id}/{span_id}"),
            "trace_path": format!(
                "/traces/{}/{trace_id}/{span_id}",
                fixture["service_name"].as_str().unwrap()
            ),
        })
    );

    let selected = evaluation.spans(json!({"span_ids": [span_id]})).await;
    assert_eq!(selected.status, StatusCode::OK, "{}", selected.body);
    assert_eq!(selected.body["subject"], manifest.body["subject"]);
    assert_eq!(selected.body["missing_span_ids"], json!([]));
}

#[tokio::test]
async fn evidence_of_another_service_is_not_the_bound_evidence() {
    let mut evaluation = Evaluation::new().await;
    let fixture = fixture("multi_tool_first_failure");
    evaluation.store(&fixture);
    // The trace and span exist, under another service than the binding names.
    let mut reference = span_reference(&fixture["spans"][0]);
    reference["service_name"] = json!("another-service");
    evaluation.bind(&reference).await;

    assert_no_attempt_evidence(&evaluation.manifest().await);
    assert_no_attempt_evidence(
        &evaluation
            .spans(json!({"span_ids": [fixture["spans"][0]["span_id"]]}))
            .await,
    );
}

#[tokio::test]
async fn an_attempt_with_no_stored_evidence_is_not_found() {
    let evaluation = Evaluation::new().await;
    let selection = json!({"span_ids": [NOT_STORED_SPAN_ID]});

    // No binding yet.
    assert_no_attempt_evidence(&evaluation.manifest().await);
    assert_no_attempt_evidence(&evaluation.spans(selection.clone()).await);

    // No such Attempt.
    let unknown = send(
        &evaluation.router,
        get(
            &format!("{ATTEMPT_EVIDENCE}/missing/manifest"),
            Some(&evaluation.cookie),
        ),
    )
    .await;
    assert_no_attempt_evidence(&unknown);

    // Bound to a span whose trace is not stored, and to an execution no
    // owner span records.
    evaluation
        .bind(&json!({
            "kind": "otel_span",
            "service_namespace": "",
            "service_name": "checkout",
            "trace_id": "a".repeat(32),
            "span_id": "b".repeat(16),
        }))
        .await;
    assert_no_attempt_evidence(&evaluation.manifest().await);
    assert_no_attempt_evidence(&evaluation.spans(selection).await);
}

#[tokio::test]
async fn an_ambiguous_bound_execution_is_a_conflict_on_both_routes() {
    let mut evaluation = Evaluation::new().await;
    let owner = |trace_id: &str, span_id: &str| {
        TestSpan {
            resource_attributes: json!({"service.name": "checkout"}).to_string(),
            ..TestSpan::new(trace_id, span_id, "checkout")
        }
        .attributes(
            &json!({
                "junjo.telemetry.contract_version": 3,
                "junjo.span_type": "workflow",
                "junjo.executable_runtime_id": "run-1",
            })
            .to_string(),
        )
    };
    // Two owner spans claim one runtime identity.
    evaluation.app.index_cold_file(
        "duplicated.parquet",
        &[
            owner(&"1".repeat(32), &"a".repeat(16)),
            owner(&"2".repeat(32), &"b".repeat(16)),
        ],
    );
    evaluation
        .bind(&json!({
            "kind": "junjo_execution",
            "service_namespace": "",
            "service_name": "checkout",
            "executable_type": "workflow",
            "runtime_id": "run-1",
        }))
        .await;

    let conflict = json!({
        "code": "ambiguous_execution_identity",
        "message": "Execution identity resolved to multiple owner spans.",
        "match_count": 2,
    });
    let manifest = evaluation.manifest().await;
    assert_eq!(manifest.status, StatusCode::CONFLICT, "{}", manifest.body);
    assert_eq!(manifest.body, conflict);
    let selected = evaluation
        .spans(json!({"span_ids": [NOT_STORED_SPAN_ID]}))
        .await;
    assert_eq!(selected.status, StatusCode::CONFLICT, "{}", selected.body);
    assert_eq!(selected.body, conflict);
}

#[tokio::test]
async fn a_span_selection_is_one_or_more_distinct_span_identifiers() {
    let evaluation = Evaluation::new().await;
    for body in [
        json!({"span_ids": []}),
        json!({"span_ids": ["a".repeat(16), "a".repeat(16)]}),
        json!({"span_ids": ["A".repeat(16)]}),
        json!({"span_ids": ["a".repeat(15)]}),
        json!({"span_ids": ["a".repeat(16)], "trace_id": "a".repeat(32)}),
        json!({}),
    ] {
        let reply = evaluation.spans(body.clone()).await;
        assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY, "{body}");
        assert_eq!(reply.body["code"], "invalid_request", "{body}");
    }
    let too_long = send(
        &evaluation.router,
        get(
            &format!("{ATTEMPT_EVIDENCE}/{}/manifest", "a".repeat(65)),
            Some(&evaluation.cookie),
        ),
    )
    .await;
    assert_eq!(too_long.status, StatusCode::UNPROCESSABLE_ENTITY);
}
