//! Contract tests for evaluation control, through the router.

use axum::Router;
use axum::body::Body;
use axum::http::header::{CONTENT_TYPE, COOKIE, WWW_AUTHENTICATE};
use axum::http::{Method, Request, StatusCode};
use junjo_evidence::trace_evidence::assembler::percent_encode;
use rusqlite::params;
use serde_json::{Value, json};

use super::schemas::{CanonicalJson, MAX_JSON_BYTES};
use super::{decode_membership_cursor, encode_membership_cursor, repo};
use crate::pagination::{Cursor, InvalidCursor, encode_cursor};
use crate::test_http::{Reply, app, get, post, request, send, sign_up, with_authorization};
use crate::test_support::TestApp;

const DATASETS: &str = "/api/v1/evaluation/datasets";
const RUNS: &str = "/api/v1/evaluation/runs";
const ATTEMPTS: &str = "/api/v1/evaluation/attempts";
const MEMBERSHIP: &str = "/api/v1/evaluation/evidence-membership";
const TOKENS: &str = "/api/v1/evaluation-tokens";
const REVISION: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const OTHER_REVISION: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const EARLIER: &str = "2020-01-01T00:00:00Z";

fn dataset_body(key: &str) -> Value {
    json!({
        "application_key": "ai_chat",
        "key": key,
        "name": "Local place realism",
        "description": "Require one specific plausible nearby place.",
    })
}

/// An authored case.
fn case_body(case_key: &str) -> Value {
    json!({
        "case_key": case_key,
        "evaluation_name": "Response place realism",
        "origin": "authored",
        "target_kind": "node",
        "target_key": "date_response_node",
        "target_name": "CreateDateIdeaResponseNode",
        "input_version": 1,
        "input_json": {"prompt": "Name one specific plausible nearby place."},
        "expectation_json": {"rubric": "Names one specific place."},
        "evaluator_key": "response_quality",
        "evaluator_version": 1,
    })
}

/// A case generated from `evidence`.
fn generated_case_body(case_key: &str, evidence: &Value) -> Value {
    let mut case = case_body(case_key);
    case["origin"] = json!("generated");
    case["source_evidence"] = evidence.clone();
    case["source_revision"] = json!(REVISION);
    case
}

/// One case with some members replaced.
fn case_with(changes: Value) -> Value {
    let mut case = case_body("specific_place_1");
    for (name, value) in changes.as_object().unwrap() {
        case[name] = value.clone();
    }
    case
}

fn run_body(dataset_id: &str, request_key: &str) -> Value {
    json!({
        "dataset_id": dataset_id,
        "request_key": request_key,
        "run_label": "baseline",
        "source_revision": REVISION,
    })
}

fn execution(runtime_id: &str) -> Value {
    json!({
        "kind": "junjo_execution",
        "service_namespace": "junjo.examples",
        "service_name": "ai-chat-evaluation",
        "executable_type": "workflow",
        "runtime_id": runtime_id,
    })
}

fn span(trace_id: &str, span_id: &str) -> Value {
    json!({
        "kind": "otel_span",
        "service_namespace": "junjo.examples",
        "service_name": "base-openai-agents",
        "trace_id": trace_id,
        "span_id": span_id,
    })
}

/// A query string from names and values.
fn query(parameters: &[(&str, &str)]) -> String {
    parameters
        .iter()
        .map(|(name, value)| format!("{name}={}", percent_encode(value)))
        .collect::<Vec<_>>()
        .join("&")
}

/// The membership lookup for one evidence reference.
fn membership_uri(evidence: &Value) -> String {
    let parameters: Vec<(&str, &str)> = evidence
        .as_object()
        .unwrap()
        .iter()
        .map(|(name, value)| (name.as_str(), value.as_str().unwrap()))
        .collect();
    format!("{MEMBERSHIP}?{}", query(&parameters))
}

/// The body of a reply that must be a success.
fn ok(reply: Reply) -> Value {
    assert_eq!(reply.status, StatusCode::OK, "{}", reply.body);
    reply.body
}

fn assert_conflict(reply: &Reply, code: &str, message: &str) {
    assert_eq!(reply.status, StatusCode::CONFLICT, "{}", reply.body);
    assert_eq!(reply.body, json!({"code": code, "message": message}));
}

fn assert_not_found(reply: &Reply, message: &str) {
    assert_eq!(reply.status, StatusCode::NOT_FOUND, "{}", reply.body);
    assert_eq!(reply.body, json!({"code": "not_found", "message": message}));
}

/// Assert a reply refuses the request as invalid. Returns the message.
fn invalid(reply: &Reply, context: &str) -> String {
    assert_eq!(
        reply.status,
        StatusCode::UNPROCESSABLE_ENTITY,
        "{context}: {}",
        reply.body
    );
    assert_eq!(reply.body["code"], "invalid_request", "{context}");
    reply.body["message"].as_str().unwrap().to_string()
}

fn id(record: &Value) -> &str {
    record["id"].as_str().unwrap()
}

fn member_names(object: &Value) -> Vec<&str> {
    object
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect()
}

/// The values of one member across a list of objects.
fn each<'a>(items: &'a Value, pointer: &str) -> Vec<&'a Value> {
    items
        .as_array()
        .unwrap()
        .iter()
        .map(|item| item.pointer(pointer).unwrap())
        .collect()
}

/// The identifiers of records in the order a listing returns them: newest
/// first, and by identifier within one second.
fn newest_first(records: &[Value]) -> Vec<String> {
    let mut positions: Vec<(&str, &str)> = records
        .iter()
        .map(|record| (record["created_at"].as_str().unwrap(), id(record)))
        .collect();
    positions.sort();
    positions
        .into_iter()
        .rev()
        .map(|(_, id)| id.to_string())
        .collect()
}

/// The text of one member across a list of objects.
fn each_text(items: &Value, pointer: &str) -> Vec<String> {
    each(items, pointer)
        .into_iter()
        .map(|value| value.as_str().unwrap().to_string())
        .collect()
}

/// One fresh application and its signed-in first user.
struct Studio {
    router: Router,
    cookie: String,
    app: TestApp,
}

impl Studio {
    async fn new() -> Self {
        let (router, app) = app();
        let cookie = sign_up(&router).await;
        Self {
            router,
            cookie,
            app,
        }
    }

    async fn get(&self, uri: &str) -> Reply {
        send(&self.router, get(uri, Some(&self.cookie))).await
    }

    async fn post(&self, uri: &str, body: Value) -> Reply {
        send(&self.router, post(uri, Some(&self.cookie), body)).await
    }

    async fn put(&self, uri: &str, body: Option<Value>) -> Reply {
        send(
            &self.router,
            request(Method::PUT, uri, Some(&self.cookie), body),
        )
        .await
    }

    /// Run one statement directly against the application database.
    async fn execute(&self, statement: &'static str) {
        self.app
            .state
            .application_db
            .writer
            .call(move |connection| connection.execute(statement, []))
            .await
            .unwrap();
    }

    /// The `Authorization` header of a new token with these scopes.
    async fn token(&self, scopes: &[&str]) -> String {
        let reply = self
            .post(TOKENS, json!({"name": scopes.join(" "), "scopes": scopes}))
            .await;
        assert_eq!(reply.status, StatusCode::CREATED, "{}", reply.body);
        format!("Bearer {}", reply.body["token"].as_str().unwrap())
    }

    async fn create_dataset(&self, key: &str) -> Value {
        ok(self.post(DATASETS, dataset_body(key)).await)
    }

    async fn add_case(&self, dataset_id: &str, case: Value) -> Reply {
        self.post(&format!("{DATASETS}/{dataset_id}/cases"), case)
            .await
    }

    async fn lock(&self, dataset_id: &str) -> Value {
        ok(self
            .put(&format!("{DATASETS}/{dataset_id}/lock"), None)
            .await)
    }

    async fn dataset_detail(&self, dataset_id: &str) -> Value {
        ok(self.get(&format!("{DATASETS}/{dataset_id}")).await)
    }

    async fn start_run(&self, dataset_id: &str, request_key: &str) -> Reply {
        self.post(RUNS, run_body(dataset_id, request_key)).await
    }

    async fn run_detail(&self, run_id: &str) -> Value {
        ok(self.get(&format!("{RUNS}/{run_id}")).await)
    }

    async fn bind(&self, attempt_id: &str, evidence: &Value) -> Reply {
        self.put(
            &format!("{ATTEMPTS}/{attempt_id}/evidence"),
            Some(json!({"evidence": evidence})),
        )
        .await
    }

    async fn record(&self, attempt_id: &str, result: Value) -> Reply {
        self.put(&format!("{ATTEMPTS}/{attempt_id}/result"), Some(result))
            .await
    }

    /// Every item of a listing, read `limit` at a time by following its
    /// cursors. `listing` ends with `?` or `&`.
    async fn all_pages(&self, listing: &str, limit: usize) -> Vec<Value> {
        let mut items = Vec::new();
        let mut uri = format!("{listing}limit={limit}");
        // A listing that never ends is a failure, not a test that hangs.
        for _ in 0..20 {
            let page = ok(self.get(&uri).await);
            let page_items = page["items"].as_array().unwrap();
            items.extend(page_items.iter().cloned());
            let Some(cursor) = page["next_cursor"].as_str() else {
                assert!(page_items.len() <= limit, "{uri}");
                return items;
            };
            assert_eq!(page_items.len(), limit, "{uri}");
            uri = format!("{listing}limit={limit}&cursor={cursor}");
        }
        panic!("{listing} did not end");
    }

    /// A locked dataset with these authored cases and one run of it. Returns
    /// the dataset and the run detail.
    async fn locked_dataset_with_run(&self, key: &str, case_keys: &[&str]) -> (Value, Value) {
        let dataset = self.create_dataset(key).await;
        for case_key in case_keys {
            ok(self.add_case(id(&dataset), case_body(case_key)).await);
        }
        let dataset = self.lock(id(&dataset)).await;
        let run = ok(self.start_run(id(&dataset), "baseline-request").await);
        (dataset, run)
    }
}

#[tokio::test]
async fn every_evaluation_route_requires_a_session_or_a_scoped_token() {
    let (router, _app) = app();
    let evidence = execution("workflow-run");
    let routes = [
        (
            Method::POST,
            DATASETS.to_string(),
            Some(dataset_body("local_place_realism_v1")),
        ),
        (
            Method::GET,
            format!("{DATASETS}?application_key=ai_chat"),
            None,
        ),
        (Method::GET, format!("{DATASETS}/dataset-id"), None),
        (
            Method::POST,
            format!("{DATASETS}/dataset-id/cases"),
            Some(case_body("specific_place_1")),
        ),
        (Method::PUT, format!("{DATASETS}/dataset-id/lock"), None),
        (
            Method::POST,
            RUNS.to_string(),
            Some(run_body("dataset-id", "baseline")),
        ),
        (Method::GET, RUNS.to_string(), None),
        (Method::GET, format!("{RUNS}/run-id"), None),
        (Method::GET, format!("{ATTEMPTS}/attempt-id"), None),
        (
            Method::PUT,
            format!("{ATTEMPTS}/attempt-id/evidence"),
            Some(json!({"evidence": evidence})),
        ),
        (
            Method::PUT,
            format!("{ATTEMPTS}/attempt-id/result"),
            Some(json!({"status": "error", "reason": "Setup failed."})),
        ),
        (Method::GET, membership_uri(&evidence), None),
    ];
    for (method, uri, body) in routes {
        let reply = send(&router, request(method.clone(), &uri, None, body)).await;
        assert_eq!(reply.status, StatusCode::UNAUTHORIZED, "{method} {uri}");
        assert_eq!(
            reply.body,
            json!({"code": "unauthorized", "message": "No valid session"}),
            "{method} {uri}"
        );
    }

    // The caller is identified before the request is read.
    let unreadable = send(&router, post(DATASETS, None, json!({"key": 7}))).await;
    assert_eq!(unreadable.status, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn a_token_needs_the_scope_of_the_route_it_calls() {
    let studio = Studio::new().await;
    let read = studio.token(&["evaluation:read"]).await;
    let write = studio.token(&["evaluation:write"]).await;
    let evidence_only = studio.token(&["evidence:read"]).await;
    let evidence = execution("workflow-run");

    let created = send(
        &studio.router,
        with_authorization(
            Method::POST,
            DATASETS,
            &write,
            Some(dataset_body("token_dataset")),
        ),
    )
    .await;
    let dataset = ok(created);
    // A token acts as the user who created it.
    let by_session = studio.create_dataset("session_dataset").await;
    assert_eq!(
        dataset["created_by_user_id"],
        by_session["created_by_user_id"]
    );

    let listed = send(
        &studio.router,
        with_authorization(Method::GET, DATASETS, &read, None),
    )
    .await;
    assert_eq!(ok(listed)["items"].as_array().unwrap().len(), 2);

    let write_routes = [
        (
            Method::POST,
            DATASETS.to_string(),
            Some(dataset_body("another")),
        ),
        (
            Method::POST,
            format!("{DATASETS}/{}/cases", id(&dataset)),
            Some(case_body("specific_place_1")),
        ),
        (
            Method::PUT,
            format!("{DATASETS}/{}/lock", id(&dataset)),
            None,
        ),
        (
            Method::POST,
            RUNS.to_string(),
            Some(run_body(id(&dataset), "baseline")),
        ),
        (
            Method::PUT,
            format!("{ATTEMPTS}/attempt-id/evidence"),
            Some(json!({"evidence": evidence})),
        ),
        (
            Method::PUT,
            format!("{ATTEMPTS}/attempt-id/result"),
            Some(json!({"status": "error", "reason": "Setup failed."})),
        ),
    ];
    let read_routes = [
        (Method::GET, DATASETS.to_string(), None),
        (Method::GET, format!("{DATASETS}/{}", id(&dataset)), None),
        (Method::GET, RUNS.to_string(), None),
        (Method::GET, format!("{RUNS}/run-id"), None),
        (Method::GET, format!("{ATTEMPTS}/attempt-id"), None),
        (Method::GET, membership_uri(&evidence), None),
    ];
    let missing_scope = |scope: &str| {
        json!({
            "code": "insufficient_evaluation_token_scope",
            "message": "Evaluation token lacks the required scope.",
            "missing_scopes": [scope],
        })
    };
    for (routes, required, allowed, other) in [
        (&write_routes, "evaluation:write", &write, &read),
        (&read_routes, "evaluation:read", &read, &write),
    ] {
        for (method, uri, body) in routes {
            for refused in [other, &evidence_only] {
                let reply = send(
                    &studio.router,
                    with_authorization(method.clone(), uri, refused, body.clone()),
                )
                .await;
                assert_eq!(reply.status, StatusCode::FORBIDDEN, "{method} {uri}");
                assert_eq!(reply.body, missing_scope(required), "{method} {uri}");
            }
            let reply = send(
                &studio.router,
                with_authorization(method.clone(), uri, allowed, body.clone()),
            )
            .await;
            assert!(
                reply.status != StatusCode::UNAUTHORIZED && reply.status != StatusCode::FORBIDDEN,
                "{method} {uri}: {}",
                reply.body
            );
        }
    }

    let unknown = send(
        &studio.router,
        with_authorization(Method::GET, DATASETS, "Bearer jcli_not_a_token", None),
    )
    .await;
    assert_eq!(unknown.status, StatusCode::UNAUTHORIZED);
    assert_eq!(unknown.headers[WWW_AUTHENTICATE], "Bearer");
}

#[tokio::test]
async fn the_headless_loop_returns_the_documented_envelopes() {
    let studio = Studio::new().await;
    let dataset = studio.create_dataset("local_place_realism_v1").await;
    assert_eq!(
        member_names(&dataset),
        [
            "id",
            "application_key",
            "key",
            "name",
            "status",
            "description",
            "created_by_user_id",
            "created_at",
            "locked_at"
        ]
    );
    assert_eq!(id(&dataset).len(), 22);
    assert_eq!(dataset["status"], "draft");
    assert_eq!(dataset["locked_at"], Value::Null);
    assert!(dataset["created_by_user_id"].is_string());
    // Timestamps are UTC at whole seconds.
    let created_at = dataset["created_at"].as_str().unwrap();
    assert!(
        created_at.len() == 20 && created_at.ends_with('Z'),
        "{created_at}"
    );
    assert_eq!(
        studio.dataset_detail(id(&dataset)).await,
        json!({"dataset": dataset, "cases": []})
    );

    let draft_run = studio.start_run(id(&dataset), "baseline").await;
    assert_conflict(
        &draft_run,
        "dataset_not_locked",
        "A run may start only from a locked dataset.",
    );

    let case = ok(studio
        .add_case(id(&dataset), case_body("specific_place_1"))
        .await);
    assert_eq!(
        member_names(&case),
        [
            "id",
            "dataset_id",
            "case_key",
            "evaluation_name",
            "ordinal",
            "origin",
            "target_kind",
            "target_key",
            "target_name",
            "input_version",
            "input_json",
            "expectation_json",
            "evaluator_key",
            "evaluator_version",
            "source_evidence",
            "source_revision",
            "created_at"
        ]
    );
    assert_eq!(case["ordinal"], 1);
    assert_eq!(case["dataset_id"], dataset["id"]);
    assert_eq!(
        case["input_json"],
        json!({"prompt": "Name one specific plausible nearby place."})
    );
    assert_eq!(case["source_evidence"], Value::Null);
    assert_eq!(case["source_revision"], Value::Null);

    let locked = studio.lock(id(&dataset)).await;
    assert_eq!(locked["status"], "locked");
    assert!(locked["locked_at"].is_string());

    let identical_case = ok(studio
        .add_case(id(&dataset), case_body("specific_place_1"))
        .await);
    assert_eq!(identical_case, case);

    let run_detail = ok(studio.start_run(id(&dataset), "baseline").await);
    assert_eq!(member_names(&run_detail), ["run", "dataset", "cases"]);
    assert_eq!(
        member_names(&run_detail["run"]),
        [
            "id",
            "dataset_id",
            "request_key",
            "run_label",
            "source_revision",
            "status",
            "created_by_user_id",
            "created_at",
            "completed_at"
        ]
    );
    assert_eq!(run_detail["run"]["status"], "active");
    assert_eq!(run_detail["run"]["completed_at"], Value::Null);
    assert_eq!(run_detail["dataset"], locked);
    let run_cases = run_detail["cases"].as_array().unwrap();
    assert_eq!(run_cases.len(), 1);
    assert_eq!(run_cases[0]["case"], case);
    let attempt = &run_cases[0]["attempt"];
    let run_id = id(&run_detail["run"]);
    assert_eq!(
        *attempt,
        json!({
            "id": attempt["id"],
            "run_id": run_id,
            "case_id": case["id"],
            "status": "queued",
            "reason": null,
            "duration_ms": null,
            "subject_evidence": null,
            "evidence_bound_at": null,
            "recorded_at": null,
        })
    );
    let attempt_id = id(attempt);

    let attempt_detail = ok(studio.get(&format!("{ATTEMPTS}/{attempt_id}")).await);
    assert_eq!(
        attempt_detail,
        json!({
            "run": run_detail["run"],
            "dataset": locked,
            "case": case,
            "attempt": attempt,
        })
    );
    assert_eq!(
        member_names(&attempt_detail),
        ["run", "dataset", "case", "attempt"]
    );

    let evidence = execution("workflow-run");
    let bound = ok(studio.bind(attempt_id, &evidence).await);
    assert_eq!(bound["subject_evidence"], evidence);
    assert_eq!(
        member_names(&bound["subject_evidence"]),
        [
            "kind",
            "service_namespace",
            "service_name",
            "executable_type",
            "runtime_id"
        ]
    );

    let recorded = ok(studio
        .record(
            attempt_id,
            json!({
                "status": "passed",
                "reason": "The response names a specific plausible place.",
            }),
        )
        .await);
    assert_eq!(recorded["status"], "passed");
    assert_eq!(recorded["duration_ms"], Value::Null);

    let completed = studio.run_detail(run_id).await;
    assert_eq!(completed["run"]["status"], "completed");
    assert_eq!(completed["cases"][0]["attempt"], recorded);

    let listed = ok(studio
        .get(&format!("{RUNS}?dataset_id={}", id(&dataset)))
        .await);
    assert_eq!(member_names(&listed), ["scope", "items", "next_cursor"]);
    assert_eq!(
        listed["scope"],
        json!({
            "dataset_id": dataset["id"],
            "target_kind": null,
            "target_key": null,
            "input_version": null,
            "evaluation_name": null,
        })
    );
    assert_eq!(listed["next_cursor"], Value::Null);
    let item = &listed["items"][0];
    assert_eq!(
        member_names(item),
        [
            "run",
            "dataset",
            "outcome_summary",
            "target_facets",
            "evaluation_facets"
        ]
    );
    assert_eq!(item["run"], completed["run"]);
    assert_eq!(
        item["dataset"],
        json!({
            "id": dataset["id"],
            "application_key": "ai_chat",
            "key": "local_place_realism_v1",
            "name": "Local place realism",
            "status": "locked",
        })
    );
    assert_eq!(
        item["outcome_summary"],
        json!({
            "total": 1,
            "queued": 0,
            "judged": 1,
            "passed": 1,
            "failed": 0,
            "error": 0,
            "pass_rate": 1.0,
            "coverage": 1.0,
        })
    );
    assert_eq!(
        item["target_facets"],
        json!([{
            "target_kind": "node",
            "target_key": "date_response_node",
            "target_name": "CreateDateIdeaResponseNode",
            "input_version": 1,
            "case_count": 1,
        }])
    );
    assert_eq!(
        item["evaluation_facets"],
        json!([{"evaluation_name": "Response place realism", "case_count": 1}])
    );

    let scope = query(&[
        ("dataset_id", id(&dataset)),
        ("target_kind", "node"),
        ("target_key", "date_response_node"),
        ("input_version", "1"),
        ("evaluation_name", "Response place realism"),
    ]);
    let scoped = ok(studio.get(&format!("{RUNS}?{scope}")).await);
    assert_eq!(scoped["items"][0]["outcome_summary"]["pass_rate"], 1.0);
    assert_eq!(
        scoped["scope"],
        json!({
            "dataset_id": dataset["id"],
            "target_kind": "node",
            "target_key": "date_response_node",
            "input_version": 1,
            "evaluation_name": "Response place realism",
        })
    );

    let unmatched = ok(studio
        .get(&format!(
            "{RUNS}?dataset_id={}&target_kind=agent",
            id(&dataset)
        ))
        .await);
    assert_eq!(unmatched["items"], json!([]));

    let all_datasets = ok(studio.get(DATASETS).await);
    assert_eq!(
        all_datasets,
        json!({"items": [locked], "next_cursor": null})
    );

    let membership = ok(studio.get(&membership_uri(&evidence)).await);
    assert_eq!(
        membership,
        json!({
            "items": [{
                "role": "attempt_subject",
                "dataset_id": dataset["id"],
                "case_id": case["id"],
                "run_id": run_id,
                "attempt_id": attempt_id,
            }],
            "next_cursor": null,
        })
    );
}

#[tokio::test]
async fn lists_are_bounded_and_refuse_malformed_cursors() {
    let studio = Studio::new().await;
    let evidence = execution("workflow-run");
    let membership = membership_uri(&evidence);
    for listing in [
        format!("{DATASETS}?"),
        format!("{RUNS}?"),
        format!("{membership}&"),
    ] {
        for bounds in ["limit=0", "limit=101", "limit=many", "cursor="] {
            let reply = studio.get(&format!("{listing}{bounds}")).await;
            invalid(&reply, &format!("{listing}{bounds}"));
        }
        let longest = studio.get(&format!("{listing}limit=100")).await;
        assert_eq!(longest.status, StatusCode::OK, "{listing}");

        let malformed = studio.get(&format!("{listing}cursor=____")).await;
        assert_eq!(malformed.status, StatusCode::UNPROCESSABLE_ENTITY);
        assert_eq!(
            malformed.body,
            json!({"code": "invalid_request", "message": "Invalid pagination cursor"}),
            "{listing}"
        );
    }

    // A cursor belongs to the listing that issued it.
    for index in 0..2 {
        studio.create_dataset(&format!("dataset_{index}")).await;
    }
    let first_page = ok(studio.get(&format!("{DATASETS}?limit=1")).await);
    let datasets_cursor = first_page["next_cursor"].as_str().unwrap();
    let next_page = studio
        .get(&format!("{DATASETS}?limit=1&cursor={datasets_cursor}"))
        .await;
    assert_eq!(next_page.status, StatusCode::OK);
    for other_listing in [format!("{RUNS}?"), format!("{membership}&")] {
        let reply = studio
            .get(&format!("{other_listing}cursor={datasets_cursor}"))
            .await;
        assert_eq!(
            invalid(&reply, &other_listing),
            "Invalid pagination cursor",
            "{other_listing}"
        );
    }
}

#[test]
fn a_membership_cursor_round_trips_and_a_malformed_one_is_refused() {
    let cursor = |text: String| Cursor::try_from(text).unwrap();
    for role in ["attempt_subject", "case_source"] {
        let members = json!({"v": 1, "kind": "evidence-membership", "role": role, "id": "a1"});
        let position = decode_membership_cursor(&cursor(encode_cursor(&members))).unwrap();
        assert_eq!(position.role.as_str(), role);
        assert_eq!(position.record_id, "a1");
        assert_eq!(
            decode_membership_cursor(&cursor(encode_membership_cursor(&position))),
            Ok(position)
        );
    }

    let valid = json!({"v": 1, "kind": "evidence-membership", "role": "case_source", "id": "a"});
    for (member, value) in [
        ("v", json!(2)),
        ("kind", json!("runs")),
        ("role", json!("owner")),
        ("role", json!(1)),
        ("id", json!("")),
        ("id", json!(7)),
    ] {
        let mut members = valid.clone();
        members[member] = value.clone();
        assert_eq!(
            decode_membership_cursor(&cursor(encode_cursor(&members))),
            Err(InvalidCursor),
            "{member} = {value}"
        );
    }
    for text in ["____", "not base64!"] {
        assert_eq!(
            decode_membership_cursor(&cursor(text.to_string())),
            Err(InvalidCursor)
        );
    }
}

#[test]
fn the_published_document_names_every_operation_and_fixes_the_run_envelopes() {
    let document = crate::openapi::published(&crate::app::openapi()).unwrap();
    let operations = [
        (
            "/api/v1/evaluation/datasets",
            "post",
            "create_evaluation_dataset",
        ),
        (
            "/api/v1/evaluation/datasets",
            "get",
            "list_evaluation_datasets",
        ),
        (
            "/api/v1/evaluation/datasets/{dataset_id}",
            "get",
            "get_evaluation_dataset",
        ),
        (
            "/api/v1/evaluation/datasets/{dataset_id}/cases",
            "post",
            "add_evaluation_case",
        ),
        (
            "/api/v1/evaluation/datasets/{dataset_id}/lock",
            "put",
            "lock_evaluation_dataset",
        ),
        ("/api/v1/evaluation/runs", "post", "start_evaluation_run"),
        ("/api/v1/evaluation/runs", "get", "list_evaluation_runs"),
        (
            "/api/v1/evaluation/runs/{run_id}",
            "get",
            "get_evaluation_run",
        ),
        (
            "/api/v1/evaluation/attempts/{attempt_id}",
            "get",
            "get_evaluation_attempt",
        ),
        (
            "/api/v1/evaluation/attempts/{attempt_id}/evidence",
            "put",
            "bind_evaluation_attempt_evidence",
        ),
        (
            "/api/v1/evaluation/attempts/{attempt_id}/result",
            "put",
            "record_evaluation_attempt_result",
        ),
        (
            "/api/v1/evaluation/evidence-membership",
            "get",
            "find_evaluation_evidence_membership",
        ),
    ];
    for (path, method, operation_id) in operations {
        let operation = &document["paths"][path][method];
        assert_eq!(operation["operationId"], operation_id, "{method} {path}");
        assert_eq!(
            operation["security"],
            json!([{"EvaluationControlToken": []}]),
            "{method} {path}"
        );
    }

    let schemas = &document["components"]["schemas"];
    assert_eq!(
        schemas["EvaluationRunDetail"]["required"],
        json!(["run", "dataset", "cases"])
    );
    assert_eq!(
        schemas["EvaluationRunList"]["required"],
        json!(["scope", "items", "next_cursor"])
    );
    assert_eq!(
        schemas["EvaluationCaseCreate"]["properties"]["target_kind"]["enum"],
        json!(["node", "workflow", "agent"])
    );
    // A conflict keeps its own documented body.
    assert_eq!(
        document["paths"]["/api/v1/evaluation/runs"]["post"]["responses"]["409"]["content"]["application/json"]
            ["schema"]["$ref"],
        "#/components/schemas/EvaluationConflictResponse"
    );
    // Arbitrary JSON is one named component.
    assert_eq!(
        schemas["EvaluationCaseRead"]["properties"]["input_json"],
        json!({"$ref": "#/components/schemas/JsonValue"})
    );
}

#[tokio::test]
async fn case_provenance_is_all_or_none_and_matches_the_origin() {
    let studio = Studio::new().await;
    let dataset = studio.create_dataset("provenance").await;
    let evidence = execution("workflow-run");

    let authored_with_source = case_with(json!({
        "source_evidence": evidence,
        "source_revision": REVISION,
    }));
    let generated_without_source = case_with(json!({"origin": "generated"}));
    let generated_without_revision =
        case_with(json!({"origin": "generated", "source_evidence": evidence}));
    let generated_without_evidence =
        case_with(json!({"origin": "generated", "source_revision": REVISION}));
    for (case, message) in [
        (
            authored_with_source,
            "authored cases cannot include source provenance",
        ),
        (
            case_with(json!({"source_revision": REVISION})),
            "authored cases cannot include source provenance",
        ),
        (
            generated_without_source,
            "generated cases require both source_evidence and source_revision",
        ),
        (
            generated_without_revision,
            "generated cases require both source_evidence and source_revision",
        ),
        (
            generated_without_evidence,
            "generated cases require both source_evidence and source_revision",
        ),
    ] {
        let reply = studio.add_case(id(&dataset), case.clone()).await;
        assert_eq!(invalid(&reply, &case.to_string()), message);
    }

    let generated = ok(studio
        .add_case(
            id(&dataset),
            generated_case_body("specific_place_1", &evidence),
        )
        .await);
    assert_eq!(generated["origin"], "generated");
    assert_eq!(generated["source_evidence"], evidence);
    assert_eq!(generated["source_revision"], REVISION);
}

#[tokio::test]
async fn an_agent_target_case_is_accepted_and_stored() {
    let studio = Studio::new().await;
    let dataset = studio.create_dataset("agent_target").await;
    let case = ok(studio
        .add_case(
            id(&dataset),
            case_with(json!({"target_kind": "agent", "target_key": "assistant_agent"})),
        )
        .await);
    assert_eq!(case["target_kind"], "agent");

    let detail = studio.dataset_detail(id(&dataset)).await;
    assert_eq!(detail["cases"], json!([case]));

    // Every target kind is stored as it was sent.
    for kind in ["node", "workflow"] {
        let stored = ok(studio
            .add_case(
                id(&dataset),
                case_with(json!({"case_key": kind, "target_kind": kind})),
            )
            .await);
        assert_eq!(stored["target_kind"], kind);
    }
}

#[tokio::test]
async fn text_fields_are_bounded_and_have_no_surrounding_whitespace() {
    let studio = Studio::new().await;
    let dataset = studio.create_dataset("text_rules").await;

    // A target name is required display text.
    let blank = studio
        .add_case(id(&dataset), case_with(json!({"target_name": " "})))
        .await;
    assert!(invalid(&blank, "blank target name").contains("name must not be blank"));

    for (changes, rule) in [
        (json!({"case_key": ""}), "key must not be blank"),
        (
            json!({"case_key": " padded"}),
            "key must not contain surrounding whitespace",
        ),
        // The ASCII separator controls and the no-break space are whitespace.
        (
            json!({"case_key": "separated\u{1f}"}),
            "key must not contain surrounding whitespace",
        ),
        (
            json!({"case_key": "\u{a0}no_break"}),
            "key must not contain surrounding whitespace",
        ),
        (json!({"case_key": "\u{1c}\u{1d}"}), "key must not be blank"),
        (
            json!({"case_key": "k".repeat(129)}),
            "key must be at most 128 UTF-8 bytes",
        ),
        // The limit counts bytes, not characters.
        (
            json!({"case_key": "é".repeat(65)}),
            "key must be at most 128 UTF-8 bytes",
        ),
        (
            json!({"evaluation_name": "n".repeat(257)}),
            "name must be at most 256 UTF-8 bytes",
        ),
        (
            json!({"target_name": "padded\n"}),
            "name must not contain surrounding whitespace",
        ),
        (json!({"target_kind": "tool"}), "unknown variant"),
        (json!({"origin": "imported"}), "unknown variant"),
        (
            json!({"input_version": 0}),
            "version must be between 1 and 2147483647",
        ),
        (
            json!({"evaluator_version": 2147483648_i64}),
            "version must be between 1 and 2147483647",
        ),
        (json!({"input_version": "1"}), "invalid type"),
        (json!({"score": 1.0}), "unknown field"),
    ] {
        let reply = studio
            .add_case(id(&dataset), case_with(changes.clone()))
            .await;
        let message = invalid(&reply, &changes.to_string());
        assert!(message.contains(rule), "{changes}: {message}");
    }
    let missing_input = {
        let mut case = case_body("specific_place_1");
        case.as_object_mut().unwrap().remove("input_json");
        case
    };
    let reply = studio.add_case(id(&dataset), missing_input).await;
    assert!(invalid(&reply, "missing input").contains("missing field `input_json`"));

    // Whitespace inside text is content, and a zero-width space is not
    // whitespace.
    let spaced = ok(studio
        .add_case(
            id(&dataset),
            case_with(json!({"case_key": "\u{200b}two words\u{1f}inside\u{200b}"})),
        )
        .await);
    assert_eq!(spaced["case_key"], "\u{200b}two words\u{1f}inside\u{200b}");

    // The longest values are accepted.
    let longest = ok(studio
        .add_case(
            id(&dataset),
            case_with(json!({
                "case_key": "é".repeat(64),
                "evaluation_name": "n".repeat(256),
                "target_key": "k".repeat(128),
                "target_name": "n".repeat(256),
                "evaluator_key": "k".repeat(128),
                "input_version": 2147483647_i64,
                "evaluator_version": 2147483647_i64,
            })),
        )
        .await);
    assert_eq!(longest["input_version"], 2147483647_i64);

    for (body, rule) in [
        (
            json!({"application_key": "ai_chat", "key": "k", "name": "  "}),
            "name must not be blank",
        ),
        (
            json!({"application_key": "ai_chat", "key": "k", "name": "n", "description": " "}),
            "description must not contain surrounding whitespace",
        ),
        (
            json!({"application_key": "ai_chat", "key": "k", "name": "n", "description": "d".repeat(2049)}),
            "description must be at most 2048 UTF-8 bytes",
        ),
        (
            json!({"application_key": "ai_chat", "key": "k", "name": "n", "owner": "me"}),
            "unknown field",
        ),
        (
            json!({"application_key": "ai_chat", "name": "n"}),
            "missing field `key`",
        ),
    ] {
        let reply = studio.post(DATASETS, body.clone()).await;
        let message = invalid(&reply, &body.to_string());
        assert!(message.contains(rule), "{body}: {message}");
    }
    // A description may be empty, absent, or null.
    for (key, description) in [
        ("empty", json!("")),
        ("null", Value::Null),
        ("longest", json!("d".repeat(2048))),
    ] {
        let body = json!({
            "application_key": "ai_chat",
            "key": key,
            "name": "n",
            "description": description,
        });
        assert_eq!(
            ok(studio.post(DATASETS, body).await)["description"],
            description
        );
    }
    let absent = json!({"application_key": "ai_chat", "key": "absent", "name": "n"});
    assert_eq!(
        ok(studio.post(DATASETS, absent).await)["description"],
        Value::Null
    );

    for (changes, rule) in [
        (
            json!({"source_revision": "a".repeat(39)}),
            "source_revision must be 40 or 64 lowercase hexadecimal digits",
        ),
        (
            json!({"source_revision": "A".repeat(40)}),
            "source_revision must be 40 or 64 lowercase hexadecimal digits",
        ),
        (
            json!({"source_revision": format!("{}\n", "a".repeat(40))}),
            "source_revision must be 40 or 64 lowercase hexadecimal digits",
        ),
        (
            json!({"dataset_id": ""}),
            "record ID must be 1 to 64 characters",
        ),
        (
            json!({"dataset_id": "d".repeat(65)}),
            "record ID must be 1 to 64 characters",
        ),
        (json!({"run_label": ""}), "name must not be blank"),
        (json!({"request_key": " "}), "key must not be blank"),
    ] {
        let mut body = run_body(id(&dataset), "baseline");
        for (name, value) in changes.as_object().unwrap() {
            body[name] = value.clone();
        }
        let reply = studio.post(RUNS, body).await;
        let message = invalid(&reply, &changes.to_string());
        assert!(message.contains(rule), "{changes}: {message}");
    }
    // A 64-digit revision is as valid as a 40-digit one.
    let mut sha256 = run_body(id(&dataset), "sha256");
    sha256["source_revision"] = json!("c".repeat(64));
    assert_conflict(
        &studio.post(RUNS, sha256).await,
        "dataset_not_locked",
        "A run may start only from a locked dataset.",
    );

    // A record identifier in a path is 1 to 64 characters.
    let long_id = "d".repeat(65);
    for uri in [
        format!("{DATASETS}/{long_id}"),
        format!("{RUNS}/{long_id}"),
        format!("{ATTEMPTS}/{long_id}"),
    ] {
        invalid(&studio.get(&uri).await, &uri);
    }
    // The limit counts characters, not bytes.
    for longest_id in ["d".repeat(64), percent_encode(&"é".repeat(64))] {
        assert_not_found(
            &studio.get(&format!("{DATASETS}/{longest_id}")).await,
            "Dataset not found",
        );
    }
    let too_long = percent_encode(&"é".repeat(65));
    invalid(
        &studio.get(&format!("{DATASETS}/{too_long}")).await,
        "65 characters",
    );
}

#[tokio::test]
async fn json_fields_are_limited_by_their_canonical_text() {
    let studio = Studio::new().await;
    let dataset = studio.create_dataset("json_limits").await;

    // `{"value":"…"}` is 12 bytes around its text.
    let longest = "x".repeat(MAX_JSON_BYTES - 12);
    let accepted = ok(studio
        .add_case(
            id(&dataset),
            case_with(json!({"input_json": {"value": longest}})),
        )
        .await);
    assert_eq!(accepted["input_json"]["value"], longest);

    for field in ["input_json", "expectation_json"] {
        let mut case = case_body("too_long");
        case[field] = json!({"value": "x".repeat(MAX_JSON_BYTES - 11)});
        let reply = studio.add_case(id(&dataset), case).await;
        let message = invalid(&reply, field);
        assert!(
            message.contains("serialized JSON must be at most 16384 UTF-8 bytes"),
            "{message}"
        );
    }

    // The limit applies to the canonical text, not to the text sent: this
    // body is larger than the limit only because of its whitespace.
    let padded = format!(
        r#"{{"case_key": "padded", "evaluation_name": "Response place realism",
            "origin": "authored", "target_kind": "node", "target_key": "date_response_node",
            "target_name": "CreateDateIdeaResponseNode", "input_version": 1,
            "input_json": [{}1], "evaluator_key": "response_quality", "evaluator_version": 1}}"#,
        " ".repeat(MAX_JSON_BYTES)
    );
    let request = Request::builder()
        .method(Method::POST)
        .uri(format!("{DATASETS}/{}/cases", id(&dataset)))
        .header(COOKIE, &studio.cookie)
        .header(CONTENT_TYPE, "application/json")
        .body(Body::from(padded))
        .unwrap();
    let reply = send(&studio.router, request).await;
    assert_eq!(ok(reply)["input_json"], json!([1]));

    // Any JSON value is an input, and null is one. A null expectation is no
    // expectation.
    for (case_key, input) in [
        ("null", Value::Null),
        ("number", json!(1.5)),
        ("text", json!("é")),
        ("list", json!([1, "two", null, {"b": 1, "a": [true]}])),
    ] {
        let case = ok(studio
            .add_case(
                id(&dataset),
                case_with(json!({
                    "case_key": case_key,
                    "input_json": input,
                    "expectation_json": null,
                })),
            )
            .await);
        assert_eq!(case["input_json"], input, "{case_key}");
        assert_eq!(case["expectation_json"], Value::Null, "{case_key}");
    }
}

#[test]
fn canonical_json_sorts_names_and_keeps_text_unescaped() {
    let canonical = |value: Value| CanonicalJson::try_from(value).unwrap().0;
    assert_eq!(
        canonical(json!({"b": 1, "a": {"z": [3, {"y": null, "x": "é 😀"}], "é": 1.0}})),
        r#"{"a":{"z":[3,{"x":"é 😀","y":null}],"é":1.0},"b":1}"#
    );
    assert_eq!(
        canonical(json!("line\nbreak \u{1f}")),
        r#""line\nbreak \u001f""#
    );
    assert_eq!(canonical(Value::Null), "null");

    // Canonical text is stable: parsing it and writing it again changes
    // nothing. Stored cases are compared on that.
    for text in [
        r#"{"a":{"z":[3,{"x":"é 😀","y":null}],"é":1.0},"b":1}"#,
        "[0,-1,1.5,1e+16,0.00001,18446744073709551615,-9223372036854775808]",
    ] {
        let value: Value = serde_json::from_str(text).unwrap();
        assert_eq!(value.to_string(), text);
        assert_eq!(canonical(value), text);
    }

    let longest = json!("x".repeat(MAX_JSON_BYTES - 2));
    assert_eq!(canonical(longest).len(), MAX_JSON_BYTES);
    let too_long = json!("x".repeat(MAX_JSON_BYTES - 1));
    assert_eq!(
        CanonicalJson::try_from(too_long),
        Err("serialized JSON must be at most 16384 UTF-8 bytes".to_string())
    );
    // The limit counts bytes: each of these characters is two.
    let multibyte = json!("é".repeat(MAX_JSON_BYTES / 2));
    assert!(CanonicalJson::try_from(multibyte).is_err());
}

#[tokio::test]
async fn a_case_is_the_same_when_its_canonical_json_is_the_same() {
    let studio = Studio::new().await;
    let dataset = studio.create_dataset("same_content").await;
    let first = ok(studio
        .add_case(
            id(&dataset),
            case_with(json!({
                "input_json": {"b": [1, {"d": 1, "c": 2}], "a": "é"},
                "expectation_json": {"rubric": 1.5},
            })),
        )
        .await);
    // Stored and returned with object names in order.
    assert_eq!(
        first["input_json"].to_string(),
        r#"{"a":"é","b":[1,{"c":2,"d":1}]}"#
    );

    // Member order is not content.
    let reordered = ok(studio
        .add_case(
            id(&dataset),
            case_with(json!({
                "input_json": {"a": "é", "b": [1, {"c": 2, "d": 1}]},
                "expectation_json": {"rubric": 1.5},
            })),
        )
        .await);
    assert_eq!(reordered, first);

    for changes in [
        // An integer and a decimal are different text.
        json!({
            "input_json": {"a": "é", "b": [1.0, {"c": 2, "d": 1}]},
            "expectation_json": {"rubric": 1.5},
        }),
        // List order is content.
        json!({
            "input_json": {"a": "é", "b": [{"c": 2, "d": 1}, 1]},
            "expectation_json": {"rubric": 1.5},
        }),
        json!({
            "input_json": {"a": "é", "b": [1, {"c": 2, "d": 1}]},
            "expectation_json": null,
        }),
        json!({
            "input_json": {"a": "é", "b": [1, {"c": 2, "d": 1}]},
            "expectation_json": {"rubric": 1.5},
            "target_name": "Another name",
        }),
    ] {
        let reply = studio.add_case(id(&dataset), case_with(changes)).await;
        assert_conflict(
            &reply,
            "case_identity_conflict",
            "Case key already exists with different content.",
        );
    }
    assert_eq!(
        studio.dataset_detail(id(&dataset)).await["cases"],
        json!([first])
    );

    // The source a case was generated from is content too.
    let source = execution("source-run");
    let generated = ok(studio
        .add_case(id(&dataset), generated_case_body("generated", &source))
        .await);
    let mut other_revision = generated_case_body("generated", &source);
    other_revision["source_revision"] = json!(OTHER_REVISION);
    for different in [
        generated_case_body("generated", &execution("other-source-run")),
        generated_case_body("generated", &span(&"1".repeat(32), &"a".repeat(16))),
        other_revision,
        case_body("generated"),
    ] {
        assert_conflict(
            &studio.add_case(id(&dataset), different).await,
            "case_identity_conflict",
            "Case key already exists with different content.",
        );
    }
    let again = ok(studio
        .add_case(id(&dataset), generated_case_body("generated", &source))
        .await);
    assert_eq!(again, generated);
}

#[tokio::test]
async fn a_result_is_binary_and_may_omit_its_duration() {
    let studio = Studio::new().await;
    let (_dataset, run) = studio
        .locked_dataset_with_run("results", &["case_1", "case_2", "case_3"])
        .await;
    let attempts = each(&run["cases"], "/attempt/id");
    let attempt_id = attempts[0].as_str().unwrap();
    ok(studio.bind(attempt_id, &execution("workflow-run")).await);

    for (result, rule) in [
        (
            json!({
                "status": "passed",
                "score": 1.0,
                "reason": "The response names a plausible specific place.",
            }),
            "unknown field `score`",
        ),
        (
            json!({"status": "queued", "reason": "Not a result."}),
            "unknown variant `queued`",
        ),
        (json!({"status": "passed"}), "missing field `reason`"),
        (
            json!({"status": "passed", "reason": ""}),
            "reason must not be blank",
        ),
        (
            json!({"status": "passed", "reason": "r".repeat(4097)}),
            "reason must be at most 4096 UTF-8 bytes",
        ),
        (
            json!({"status": "passed", "reason": "Too fast.", "duration_ms": -1}),
            "duration_ms must be between 0 and 86400000",
        ),
        (
            json!({"status": "passed", "reason": "Too slow.", "duration_ms": 86400001}),
            "duration_ms must be between 0 and 86400000",
        ),
        (
            json!({"status": "passed", "reason": "Not whole.", "duration_ms": 1.5}),
            "invalid type",
        ),
    ] {
        let reply = studio.record(attempt_id, result.clone()).await;
        let message = invalid(&reply, &result.to_string());
        assert!(message.contains(rule), "{result}: {message}");
    }

    let recorded = ok(studio
        .record(
            attempt_id,
            json!({
                "status": "passed",
                "reason": "The response names a plausible specific place.",
            }),
        )
        .await);
    assert_eq!(recorded["duration_ms"], Value::Null);
    assert!(recorded["recorded_at"].is_string());

    // The bounds of a duration are accepted.
    for (attempt, duration_ms) in [(attempts[1], 0), (attempts[2], 86_400_000)] {
        let result = json!({
            "status": "error",
            "reason": "r".repeat(4096),
            "duration_ms": duration_ms,
        });
        let recorded = ok(studio.record(attempt.as_str().unwrap(), result).await);
        assert_eq!(recorded["duration_ms"], duration_ms);
    }
}

#[tokio::test]
async fn an_evidence_reference_is_exact_and_names_one_kind() {
    let studio = Studio::new().await;
    let (_dataset, run) = studio
        .locked_dataset_with_run("references", &["case_1", "case_2"])
        .await;
    let attempts = each(&run["cases"], "/attempt/id");
    let attempt_id = attempts[0].as_str().unwrap();
    let evidence_with = |changes: Value| {
        let mut evidence = execution("workflow-run");
        for (name, value) in changes.as_object().unwrap() {
            evidence[name] = value.clone();
        }
        evidence
    };
    let without_kind = {
        let mut evidence = execution("workflow-run");
        evidence.as_object_mut().unwrap().remove("kind");
        evidence
    };
    let span_with_runtime_id = {
        let mut evidence = span(&"1".repeat(32), &"a".repeat(16));
        evidence["runtime_id"] = json!("workflow-run");
        evidence
    };

    for (evidence, rule) in [
        (
            evidence_with(json!({"service_namespace": " junjo.examples"})),
            "service_namespace must not contain surrounding whitespace",
        ),
        (
            evidence_with(json!({"service_namespace": "n".repeat(257)})),
            "service_namespace must be at most 256 UTF-8 bytes",
        ),
        (
            evidence_with(json!({"service_name": ""})),
            "execution identity must not be blank",
        ),
        (
            evidence_with(json!({"runtime_id": "r".repeat(257)})),
            "execution identity must be at most 256 UTF-8 bytes",
        ),
        (
            evidence_with(json!({"executable_type": "node"})),
            "unknown variant `node`",
        ),
        (
            evidence_with(json!({"kind": "trace"})),
            "kind must be junjo_execution or otel_span",
        ),
        (without_kind, "kind must be junjo_execution or otel_span"),
        (
            evidence_with(json!({"trace_id": "1".repeat(32)})),
            "unknown field `trace_id`",
        ),
        (span_with_runtime_id, "unknown field `runtime_id`"),
        (
            span(&"1".repeat(31), &"a".repeat(16)),
            "trace_id must be 32 lowercase hexadecimal digits",
        ),
        (
            span(&"G".repeat(32), &"a".repeat(16)),
            "trace_id must be 32 lowercase hexadecimal digits",
        ),
        (
            span(&"1".repeat(32), &"A".repeat(16)),
            "span_id must be 16 lowercase hexadecimal digits",
        ),
    ] {
        let reply = studio.bind(attempt_id, &evidence).await;
        let message = invalid(&reply, &evidence.to_string());
        assert!(message.contains(rule), "{evidence}: {message}");
    }
    let unreadable = studio
        .put(
            &format!("{ATTEMPTS}/{attempt_id}/evidence"),
            Some(json!({"evidence": execution("workflow-run"), "note": "extra"})),
        )
        .await;
    assert!(invalid(&unreadable, "extra member").contains("unknown field `note`"));

    // An empty namespace is explicit, and is not the same as another one.
    let no_namespace = evidence_with(json!({"service_namespace": ""}));
    let bound = ok(studio.bind(attempt_id, &no_namespace).await);
    assert_eq!(bound["subject_evidence"], no_namespace);
    let named = ok(studio
        .bind(attempts[1].as_str().unwrap(), &execution("workflow-run"))
        .await);
    assert_eq!(
        named["subject_evidence"]["service_namespace"],
        "junjo.examples"
    );
    let found = ok(studio.get(&membership_uri(&no_namespace)).await);
    assert_eq!(each(&found["items"], "/attempt_id"), [&bound["id"]]);
}

#[tokio::test]
async fn the_control_loop_is_idempotent_and_exact() {
    let studio = Studio::new().await;
    let source = execution("source-workflow-run");
    let dataset = studio.create_dataset("local_place_realism_v1").await;
    assert_eq!(dataset["status"], "draft");
    let same_dataset = studio.create_dataset("local_place_realism_v1").await;
    assert_eq!(same_dataset, dataset);

    let case = ok(studio
        .add_case(
            id(&dataset),
            generated_case_body("specific_place_1", &source),
        )
        .await);
    assert_eq!(case["ordinal"], 1);
    assert_eq!(case["source_evidence"], source);

    let locked = studio.lock(id(&dataset)).await;
    assert_eq!(locked["status"], "locked");
    assert!(locked["locked_at"].is_string());
    // A repeated write returns the record and leaves it as it was. The
    // stored time is moved back so that a rewrite would show.
    studio
        .execute("UPDATE eval_datasets SET locked_at = '2020-01-01T00:00:00Z'")
        .await;
    assert_eq!(studio.lock(id(&dataset)).await["locked_at"], EARLIER);

    let identical_case = ok(studio
        .add_case(
            id(&dataset),
            generated_case_body("specific_place_1", &source),
        )
        .await);
    assert_eq!(identical_case, case);

    let detail = ok(studio.start_run(id(&dataset), "baseline-request").await);
    assert_eq!(each(&detail["cases"], "/case/id"), [&case["id"]]);
    assert_eq!(detail["cases"][0]["attempt"]["status"], "queued");
    let attempt_id = id(&detail["cases"][0]["attempt"]);
    let run_id = id(&detail["run"]);

    let subject = execution("subject-workflow-run");
    let bound = ok(studio.bind(attempt_id, &subject).await);
    assert_eq!(bound["subject_evidence"], subject);
    assert!(bound["evidence_bound_at"].is_string());
    studio
        .execute("UPDATE eval_case_attempts SET evidence_bound_at = '2020-01-01T00:00:00Z'")
        .await;
    assert_eq!(
        ok(studio.bind(attempt_id, &subject).await)["evidence_bound_at"],
        EARLIER
    );

    let result = json!({
        "status": "passed",
        "reason": "The response names a specific plausible place.",
    });
    let recorded = ok(studio.record(attempt_id, result.clone()).await);
    assert_eq!(recorded["duration_ms"], Value::Null);
    assert_eq!(recorded["status"], "passed");
    studio
        .execute("UPDATE eval_case_attempts SET recorded_at = '2020-01-01T00:00:00Z'")
        .await;
    studio
        .execute("UPDATE eval_runs SET completed_at = '2020-01-01T00:00:00Z'")
        .await;
    let recorded_again = ok(studio.record(attempt_id, result).await);
    assert_eq!(recorded_again["recorded_at"], EARLIER);

    let completed = studio.run_detail(run_id).await;
    assert_eq!(completed["run"]["status"], "completed");
    assert_eq!(completed["run"]["completed_at"], EARLIER);
    assert_eq!(
        completed["cases"][0]["attempt"]["subject_evidence"],
        subject
    );

    // A repeated start returns the run as it is now, not a new one.
    let resumed = ok(studio.start_run(id(&dataset), "baseline-request").await);
    assert_eq!(resumed, completed);
    assert_eq!(resumed["cases"][0]["attempt"]["status"], "passed");

    let listed = ok(studio
        .get(&format!("{RUNS}?dataset_id={}", id(&dataset)))
        .await);
    assert_eq!(listed["items"].as_array().unwrap().len(), 1);
    assert_eq!(listed["scope"]["dataset_id"], dataset["id"]);
    assert_eq!(
        listed["items"][0]["outcome_summary"],
        json!({
            "total": 1,
            "queued": 0,
            "judged": 1,
            "passed": 1,
            "failed": 0,
            "error": 0,
            "pass_rate": 1.0,
            "coverage": 1.0,
        })
    );

    let source_membership = ok(studio.get(&membership_uri(&source)).await);
    assert_eq!(
        source_membership["items"],
        json!([{
            "role": "case_source",
            "dataset_id": dataset["id"],
            "case_id": case["id"],
            "run_id": null,
            "attempt_id": null,
        }])
    );
    let subject_membership = ok(studio.get(&membership_uri(&subject)).await);
    assert_eq!(
        each(&subject_membership["items"], "/role"),
        [&json!("attempt_subject")]
    );
    assert_eq!(subject_membership["items"][0]["attempt_id"], attempt_id);
}

#[tokio::test]
async fn span_evidence_is_bound_and_found_by_reverse_lookup() {
    let studio = Studio::new().await;
    let (_dataset, run) = studio
        .locked_dataset_with_run("span_subject", &["specific_place_1"])
        .await;
    let attempt_id = id(&run["cases"][0]["attempt"]);
    let evidence = span(&"1".repeat(32), &"a".repeat(16));

    let bound = ok(studio.bind(attempt_id, &evidence).await);
    assert_eq!(bound["subject_evidence"], evidence);
    assert_eq!(
        member_names(&bound["subject_evidence"]),
        [
            "kind",
            "service_namespace",
            "service_name",
            "trace_id",
            "span_id"
        ]
    );
    assert!(bound["evidence_bound_at"].is_string());

    let membership = ok(studio.get(&membership_uri(&evidence)).await);
    assert_eq!(
        each(&membership["items"], "/attempt_id"),
        [&json!(attempt_id)]
    );
    // Another span of the same trace is another execution.
    let other_span = span(&"1".repeat(32), &"b".repeat(16));
    let none = ok(studio.get(&membership_uri(&other_span)).await);
    assert_eq!(none, json!({"items": [], "next_cursor": null}));
}

#[tokio::test]
async fn span_evidence_can_identify_a_generated_case_source() {
    let studio = Studio::new().await;
    let dataset = studio.create_dataset("span_source").await;
    let evidence = span(&"2".repeat(32), &"b".repeat(16));

    let case = ok(studio
        .add_case(
            id(&dataset),
            generated_case_body("specific_place_1", &evidence),
        )
        .await);
    assert_eq!(case["source_evidence"], evidence);

    let membership = ok(studio.get(&membership_uri(&evidence)).await);
    assert_eq!(each(&membership["items"], "/role"), [&json!("case_source")]);
    assert_eq!(membership["items"][0]["case_id"], case["id"]);

    // A span that is the source of two cases and the subject of an attempt
    // is listed a page at a time: the attempt, then the cases.
    let second = ok(studio
        .add_case(
            id(&dataset),
            generated_case_body("specific_place_2", &evidence),
        )
        .await);
    studio.lock(id(&dataset)).await;
    let run = ok(studio.start_run(id(&dataset), "baseline-request").await);
    let attempt_id = id(&run["cases"][0]["attempt"]);
    ok(studio.bind(attempt_id, &evidence).await);
    let lookup = format!("{}&", membership_uri(&evidence));
    let memberships = json!(studio.all_pages(&lookup, 1).await);
    assert_eq!(
        each(&memberships, "/role"),
        [
            &json!("attempt_subject"),
            &json!("case_source"),
            &json!("case_source")
        ]
    );
    assert_eq!(memberships[0]["attempt_id"], attempt_id);
    let mut case_ids = [id(&case), id(&second)];
    case_ids.sort();
    assert_eq!(
        [&memberships[1]["case_id"], &memberships[2]["case_id"]],
        [&json!(case_ids[0]), &json!(case_ids[1])]
    );
}

#[tokio::test]
async fn a_membership_lookup_takes_exactly_the_parameters_of_its_kind() {
    let studio = Studio::new().await;
    let service = "service_namespace=junjo.examples&service_name=ai-chat-evaluation";
    let trace_id = "1".repeat(32);
    let span_id = "a".repeat(16);
    for (parameters, message) in [
        (
            format!("kind=junjo_execution&{service}&executable_type=workflow"),
            "Invalid junjo_execution evidence identity",
        ),
        (
            format!("kind=junjo_execution&{service}&runtime_id=run"),
            "Invalid junjo_execution evidence identity",
        ),
        (
            format!(
                "kind=junjo_execution&{service}&executable_type=workflow&runtime_id=run&trace_id={trace_id}"
            ),
            "Invalid junjo_execution evidence identity",
        ),
        (
            format!(
                "kind=junjo_execution&{service}&executable_type=workflow&runtime_id=run&span_id={span_id}"
            ),
            "Invalid junjo_execution evidence identity",
        ),
        (
            format!("kind=otel_span&{service}&trace_id={trace_id}"),
            "Invalid otel_span evidence identity",
        ),
        (
            format!("kind=otel_span&{service}&span_id={span_id}"),
            "Invalid otel_span evidence identity",
        ),
        (
            format!(
                "kind=otel_span&{service}&trace_id={trace_id}&span_id={span_id}&runtime_id=run"
            ),
            "Invalid otel_span evidence identity",
        ),
        (
            format!(
                "kind=otel_span&{service}&trace_id={trace_id}&span_id={span_id}&executable_type=agent"
            ),
            "Invalid otel_span evidence identity",
        ),
    ] {
        let reply = studio.get(&format!("{MEMBERSHIP}?{parameters}")).await;
        assert_eq!(invalid(&reply, &parameters), message, "{parameters}");
    }

    for (parameters, rule) in [
        (
            format!("{service}&executable_type=workflow&runtime_id=run"),
            "missing field `kind`",
        ),
        (
            format!("kind=trace&{service}&executable_type=workflow&runtime_id=run"),
            "unknown variant `trace`",
        ),
        (
            "kind=junjo_execution&service_name=ai-chat&executable_type=workflow&runtime_id=run"
                .to_string(),
            "missing field `service_namespace`",
        ),
        (
            "kind=junjo_execution&service_namespace=&executable_type=workflow&runtime_id=run"
                .to_string(),
            "missing field `service_name`",
        ),
        (
            "kind=junjo_execution&service_namespace=&service_name=&executable_type=workflow&runtime_id=run"
                .to_string(),
            "execution identity must not be blank",
        ),
        (
            format!("kind=junjo_execution&{service}&executable_type=node&runtime_id=run"),
            "unknown variant `node`",
        ),
        (
            format!("kind=otel_span&{service}&trace_id=abc&span_id={span_id}"),
            "trace_id must be 32 lowercase hexadecimal digits",
        ),
        (
            format!("kind=otel_span&{service}&trace_id={trace_id}&span_id=abc"),
            "span_id must be 16 lowercase hexadecimal digits",
        ),
    ] {
        let reply = studio.get(&format!("{MEMBERSHIP}?{parameters}")).await;
        let message = invalid(&reply, &parameters);
        assert!(message.contains(rule), "{parameters}: {message}");
    }

    // An empty namespace is sent as an empty parameter.
    let explicit = studio
        .get(&format!(
            "{MEMBERSHIP}?kind=junjo_execution&service_namespace=&service_name=ai-chat&executable_type=agent&runtime_id=run"
        ))
        .await;
    assert_eq!(ok(explicit), json!({"items": [], "next_cursor": null}));
}

#[tokio::test]
async fn conflicting_natural_keys_and_terminal_writes_are_refused() {
    let studio = Studio::new().await;
    let dataset = studio.create_dataset("local_place_realism_v1").await;

    for changes in [
        json!({"name": "Different name"}),
        json!({"description": "Different description."}),
        json!({"description": null}),
    ] {
        let mut body = dataset_body("local_place_realism_v1");
        for (name, value) in changes.as_object().unwrap() {
            body[name] = value.clone();
        }
        assert_conflict(
            &studio.post(DATASETS, body).await,
            "dataset_identity_conflict",
            "Dataset key already exists with different content.",
        );
    }
    // The same key in another application is another dataset.
    let mut elsewhere = dataset_body("local_place_realism_v1");
    elsewhere["application_key"] = json!("other_application");
    assert_ne!(
        ok(studio.post(DATASETS, elsewhere).await)["id"],
        dataset["id"]
    );

    ok(studio
        .add_case(id(&dataset), case_body("specific_place_1"))
        .await);
    assert_conflict(
        &studio
            .add_case(id(&dataset), case_with(json!({"evaluator_version": 2})))
            .await,
        "case_identity_conflict",
        "Case key already exists with different content.",
    );

    studio.lock(id(&dataset)).await;
    let run = ok(studio.start_run(id(&dataset), "baseline-request").await);
    for changes in [
        json!({"source_revision": OTHER_REVISION}),
        json!({"run_label": "candidate"}),
    ] {
        let mut body = run_body(id(&dataset), "baseline-request");
        for (name, value) in changes.as_object().unwrap() {
            body[name] = value.clone();
        }
        assert_conflict(
            &studio.post(RUNS, body).await,
            "run_identity_conflict",
            "Run request key already exists with different content.",
        );
    }

    let attempt_id = id(&run["cases"][0]["attempt"]);
    let mut subject = execution("workflow-run");
    subject["service_namespace"] = json!("");
    ok(studio.bind(attempt_id, &subject).await);
    let mut other_run = subject.clone();
    other_run["runtime_id"] = json!("other-run");
    for other in [other_run, span(&"1".repeat(32), &"a".repeat(16))] {
        assert_conflict(
            &studio.bind(attempt_id, &other).await,
            "attempt_evidence_conflict",
            "Attempt is already bound to different evidence.",
        );
    }

    let failed = json!({
        "status": "failed",
        "reason": "The response did not name a specific place.",
        "duration_ms": 20,
    });
    let recorded = ok(studio.record(attempt_id, failed.clone()).await);
    assert_eq!(recorded["duration_ms"], 20);
    for changes in [
        json!({"status": "passed"}),
        json!({"reason": "Conflicting outcome."}),
        json!({"duration_ms": 21}),
        json!({"duration_ms": null}),
    ] {
        let mut result = failed.clone();
        for (name, value) in changes.as_object().unwrap() {
            result[name] = value.clone();
        }
        assert_conflict(
            &studio.record(attempt_id, result).await,
            "attempt_result_conflict",
            "Attempt already has a different terminal result.",
        );
    }
    assert_eq!(ok(studio.record(attempt_id, failed).await), recorded);
    // The evidence a terminal attempt already has can still be confirmed.
    assert_eq!(ok(studio.bind(attempt_id, &subject).await), recorded);
}

#[tokio::test]
async fn a_judgment_needs_evidence_and_a_terminal_attempt_takes_none() {
    let studio = Studio::new().await;
    let (_dataset, run) = studio
        .locked_dataset_with_run("judgments", &["case_1", "case_2"])
        .await;
    let attempts = each(&run["cases"], "/attempt/id");
    let attempt_id = attempts[0].as_str().unwrap();

    for status in ["passed", "failed"] {
        let reply = studio
            .record(attempt_id, json!({"status": status, "reason": "Judged."}))
            .await;
        assert_conflict(
            &reply,
            "attempt_evidence_required",
            "Passed and failed attempts require bound evidence.",
        );
    }
    let errored = ok(studio
        .record(
            attempt_id,
            json!({"status": "error", "reason": "Setup failed."}),
        )
        .await);
    assert_eq!(errored["subject_evidence"], Value::Null);
    assert_conflict(
        &studio.bind(attempt_id, &execution("workflow-run")).await,
        "attempt_terminal",
        "A terminal attempt cannot acquire an evidence binding.",
    );

    // The run is active until its last attempt has a result.
    let run_id = id(&run["run"]);
    assert_eq!(studio.run_detail(run_id).await["run"]["status"], "active");
    let last = attempts[1].as_str().unwrap();
    ok(studio.bind(last, &execution("workflow-run")).await);
    ok(studio
        .record(
            last,
            json!({"status": "failed", "reason": "No place named."}),
        )
        .await);
    let completed = studio.run_detail(run_id).await;
    assert_eq!(completed["run"]["status"], "completed");
    assert!(completed["run"]["completed_at"].is_string());
    assert_eq!(
        each(&completed["cases"], "/attempt/status"),
        [&json!("error"), &json!("failed")]
    );
}

#[tokio::test]
async fn a_run_listing_counts_each_outcome() {
    let studio = Studio::new().await;
    let case_keys = ["case_1", "case_2", "case_3", "case_4", "case_5"];
    let (_dataset, run) = studio.locked_dataset_with_run("outcomes", &case_keys).await;
    let attempts = each_text(&run["cases"], "/attempt/id");
    for (index, status) in ["passed", "failed", "failed", "error"]
        .into_iter()
        .enumerate()
    {
        let evidence = execution(&format!("workflow-run-{index}"));
        ok(studio.bind(&attempts[index], &evidence).await);
        let result = json!({"status": status, "reason": "Recorded."});
        ok(studio.record(&attempts[index], result).await);
    }

    let listed = ok(studio.get(RUNS).await);
    assert_eq!(listed["items"][0]["run"]["status"], "active");
    // Judged attempts passed or failed. An error is not a judgment.
    assert_eq!(
        listed["items"][0]["outcome_summary"],
        json!({
            "total": 5,
            "queued": 1,
            "judged": 3,
            "passed": 1,
            "failed": 2,
            "error": 1,
            "pass_rate": 1.0 / 3.0,
            "coverage": 3.0 / 5.0,
        })
    );
}

#[tokio::test]
async fn a_draft_cannot_run_and_a_locked_dataset_gains_no_case() {
    let studio = Studio::new().await;
    let dataset = studio.create_dataset("local_place_realism_v1").await;
    ok(studio
        .add_case(id(&dataset), case_body("specific_place_1"))
        .await);

    assert_conflict(
        &studio.start_run(id(&dataset), "baseline-request").await,
        "dataset_not_locked",
        "A run may start only from a locked dataset.",
    );

    studio.lock(id(&dataset)).await;
    assert_conflict(
        &studio.add_case(id(&dataset), case_body("new_case")).await,
        "dataset_locked",
        "Locked datasets cannot accept new cases.",
    );

    // A locked dataset without a case cannot run either.
    let empty = studio.create_dataset("empty").await;
    studio.lock(id(&empty)).await;
    assert_conflict(
        &studio.start_run(id(&empty), "baseline-request").await,
        "dataset_empty",
        "A run requires at least one dataset case.",
    );
}

#[tokio::test]
async fn a_dataset_holds_at_most_one_hundred_cases() {
    let studio = Studio::new().await;
    let dataset = studio.create_dataset("full").await;
    for index in 1..=100 {
        let case = ok(studio
            .add_case(id(&dataset), case_body(&format!("case_{index:03}")))
            .await);
        assert_eq!(case["ordinal"], index);
    }

    assert_conflict(
        &studio.add_case(id(&dataset), case_body("over_limit")).await,
        "dataset_case_limit_reached",
        "A dataset may contain at most 100 cases.",
    );
    // A case the dataset already holds is still returned.
    let held = ok(studio.add_case(id(&dataset), case_body("case_100")).await);
    assert_eq!(held["ordinal"], 100);

    let detail = studio.dataset_detail(id(&dataset)).await;
    let ordinals: Vec<i64> = each(&detail["cases"], "/ordinal")
        .into_iter()
        .map(|ordinal| ordinal.as_i64().unwrap())
        .collect();
    assert_eq!(ordinals, (1..=100).collect::<Vec<i64>>());

    studio.lock(id(&dataset)).await;
    let run = ok(studio.start_run(id(&dataset), "baseline-request").await);
    assert_eq!(run["cases"].as_array().unwrap().len(), 100);
    assert_eq!(
        each(&run["cases"], "/case/id"),
        each(&detail["cases"], "/id")
    );
    let listed = ok(studio.get(RUNS).await);
    assert_eq!(listed["items"][0]["outcome_summary"]["total"], 100);
    assert_eq!(listed["items"][0]["outcome_summary"]["coverage"], 0.0);
    assert_eq!(listed["items"][0]["target_facets"][0]["case_count"], 100);
}

#[tokio::test]
async fn an_error_needs_no_execution_and_history_survives_its_creator() {
    let studio = Studio::new().await;
    let (dataset, run) = studio
        .locked_dataset_with_run("local_place_realism_v1", &["specific_place_1"])
        .await;
    let attempt_id = id(&run["cases"][0]["attempt"]);
    assert!(dataset["created_by_user_id"].is_string());
    assert!(run["run"]["created_by_user_id"].is_string());

    let recorded = ok(studio
        .record(
            attempt_id,
            json!({
                "status": "error",
                "reason": "Target setup failed before execution identity existed.",
            }),
        )
        .await);
    assert_eq!(recorded["subject_evidence"], Value::Null);
    assert_eq!(recorded["status"], "error");

    studio.execute("DELETE FROM users").await;
    // No user is left to sign in, so the history is read where it is stored.
    let run_id = id(&run["run"]).to_string();
    let preserved = studio
        .app
        .state
        .application_db
        .reader
        .call(move |connection| repo::get_run(connection, &run_id))
        .await
        .unwrap()
        .unwrap();
    assert_eq!(preserved.dataset.created_by_user_id, None);
    assert_eq!(preserved.run.created_by_user_id, None);
    let attempt = serde_json::to_value(&preserved.cases[0].attempt).unwrap();
    assert_eq!(attempt, recorded);
}

#[tokio::test]
async fn dataset_run_and_membership_pages_do_not_repeat_rows() {
    let studio = Studio::new().await;
    let mut datasets = Vec::new();
    for index in 0..3 {
        datasets.push(
            studio
                .create_dataset(&format!("page_dataset_{index}"))
                .await,
        );
    }
    let mut elsewhere = dataset_body("page_dataset_0");
    elsewhere["application_key"] = json!("other_application");
    let elsewhere = ok(studio.post(DATASETS, elsewhere).await);

    let pages = format!("{DATASETS}?application_key=ai_chat&limit=2");
    let first_datasets = ok(studio.get(&pages).await);
    assert_eq!(first_datasets["items"].as_array().unwrap().len(), 2);
    let cursor = first_datasets["next_cursor"].as_str().unwrap();
    let second_datasets = ok(studio.get(&format!("{pages}&cursor={cursor}")).await);
    assert_eq!(second_datasets["items"].as_array().unwrap().len(), 1);
    assert_eq!(second_datasets["next_cursor"], Value::Null);
    let mut listed = each_text(&first_datasets["items"], "/id");
    listed.extend(each_text(&second_datasets["items"], "/id"));
    assert_eq!(listed, newest_first(&datasets));
    // Without the application key the listing covers every application.
    let everything = ok(studio.get(DATASETS).await);
    assert_eq!(everything["items"].as_array().unwrap().len(), 4);
    assert!(each(&everything["items"], "/id").contains(&&elsewhere["id"]));

    let source = execution("shared-source-run");
    let selected = &datasets[0];
    let mut case_ids = Vec::new();
    for index in 0..2 {
        let case = ok(studio
            .add_case(
                id(selected),
                generated_case_body(&format!("generated_{index}"), &source),
            )
            .await);
        case_ids.push(case["id"].clone());
    }
    studio.lock(id(selected)).await;
    let mut runs = Vec::new();
    for index in 0..2 {
        let run = ok(studio
            .start_run(id(selected), &format!("run_page_{index}"))
            .await);
        runs.push(run["run"].clone());
    }
    let run_ids = newest_first(&runs);
    // With and without the dataset filter.
    for listing in [
        format!("{RUNS}?dataset_id={}&", id(selected)),
        format!("{RUNS}?"),
    ] {
        let listed = json!(studio.all_pages(&listing, 1).await);
        assert_eq!(each_text(&listed, "/run/id"), run_ids, "{listing}");
    }

    // The execution the cases came from is also the subject of an attempt.
    let first_run = studio.run_detail(&run_ids[0]).await;
    let attempt_id = id(&first_run["cases"][0]["attempt"]).to_string();
    ok(studio.bind(&attempt_id, &source).await);

    let lookup = membership_uri(&source);
    let memberships = studio.all_pages(&format!("{lookup}&"), 1).await;
    // The attempt first, then the cases in identifier order.
    case_ids.sort_by(|left, right| left.as_str().cmp(&right.as_str()));
    assert_eq!(
        memberships,
        [
            json!({
                "role": "attempt_subject",
                "dataset_id": selected["id"],
                "case_id": first_run["cases"][0]["case"]["id"],
                "run_id": run_ids[0],
                "attempt_id": attempt_id,
            }),
            json!({
                "role": "case_source",
                "dataset_id": selected["id"],
                "case_id": case_ids[0],
                "run_id": null,
                "attempt_id": null,
            }),
            json!({
                "role": "case_source",
                "dataset_id": selected["id"],
                "case_id": case_ids[1],
                "run_id": null,
                "attempt_id": null,
            }),
        ]
    );
    let whole = ok(studio.get(&lookup).await);
    assert_eq!(whole["items"], json!(memberships));
    assert_eq!(whole["next_cursor"], Value::Null);
}

#[tokio::test]
async fn listings_are_newest_first() {
    let studio = Studio::new().await;
    let mut dataset_ids = Vec::new();
    for index in 0..3 {
        let dataset = studio.create_dataset(&format!("dataset_{index}")).await;
        dataset_ids.push(id(&dataset).to_string());
    }
    // Give each record its own second, oldest first.
    for (index, dataset_id) in dataset_ids.iter().enumerate() {
        let created_at = format!("2025-01-15T10:30:0{index}Z");
        let dataset_id = dataset_id.clone();
        studio
            .app
            .state
            .application_db
            .writer
            .call(move |connection| {
                connection.execute(
                    "UPDATE eval_datasets SET created_at = ?1 WHERE id = ?2",
                    params![created_at, dataset_id],
                )
            })
            .await
            .unwrap();
    }
    let expected: Vec<String> = dataset_ids.iter().rev().cloned().collect();
    for listing in [
        format!("{DATASETS}?"),
        format!("{DATASETS}?application_key=ai_chat&"),
    ] {
        let whole = ok(studio.get(&listing).await);
        assert_eq!(each_text(&whole["items"], "/id"), expected, "{listing}");
        assert_eq!(
            whole["items"][0]["created_at"], "2025-01-15T10:30:02Z",
            "{listing}"
        );

        let paged = json!(studio.all_pages(&listing, 1).await);
        assert_eq!(each_text(&paged, "/id"), expected, "{listing}");
    }

    let dataset_id = &dataset_ids[0];
    ok(studio.add_case(dataset_id, case_body("case_1")).await);
    studio.lock(dataset_id).await;
    let mut run_ids = Vec::new();
    for index in 0..3 {
        let run = ok(studio.start_run(dataset_id, &format!("run_{index}")).await);
        run_ids.push(id(&run["run"]).to_string());
    }
    for (index, run_id) in run_ids.iter().enumerate() {
        let created_at = format!("2025-01-15T10:30:0{index}Z");
        let run_id = run_id.clone();
        studio
            .app
            .state
            .application_db
            .writer
            .call(move |connection| {
                connection.execute(
                    "UPDATE eval_runs SET created_at = ?1 WHERE id = ?2",
                    params![created_at, run_id],
                )
            })
            .await
            .unwrap();
    }
    let expected: Vec<String> = run_ids.iter().rev().cloned().collect();
    for listing in [
        format!("{RUNS}?"),
        format!("{RUNS}?dataset_id={dataset_id}&"),
        format!("{RUNS}?target_kind=node&"),
    ] {
        let whole = ok(studio.get(&listing).await);
        assert_eq!(each_text(&whole["items"], "/run/id"), expected, "{listing}");

        let paged = json!(studio.all_pages(&listing, 2).await);
        assert_eq!(each_text(&paged, "/run/id"), expected, "{listing}");
    }
}

#[tokio::test]
async fn run_scope_filters_must_match_the_same_case() {
    let studio = Studio::new().await;
    let dataset = studio.create_dataset("mixed_targets").await;
    ok(studio
        .add_case(
            id(&dataset),
            case_with(json!({
                "case_key": "node_case",
                "evaluator_key": "node_quality",
                "evaluation_name": "Node place realism",
            })),
        )
        .await);
    ok(studio
        .add_case(
            id(&dataset),
            case_with(json!({
                "case_key": "agent_case",
                "target_kind": "agent",
                "target_key": "chat_agent",
                "target_name": "AI Chat Agent",
                "evaluator_key": "agent_quality",
                "evaluation_name": "Agent place realism",
            })),
        )
        .await);
    ok(studio
        .add_case(
            id(&dataset),
            case_with(json!({
                "case_key": "second_agent_case",
                "target_kind": "agent",
                "target_key": "chat_agent",
                "target_name": "AI Chat Agent",
                "evaluator_key": "agent_quality",
                "evaluation_name": "Agent place realism",
                "input_version": 2,
            })),
        )
        .await);
    studio.lock(id(&dataset)).await;
    let run = ok(studio.start_run(id(&dataset), "baseline-request").await);
    let agent_attempt = id(&run["cases"][1]["attempt"]);
    ok(studio.bind(agent_attempt, &execution("agent-run")).await);
    ok(studio
        .record(
            agent_attempt,
            json!({"status": "passed", "reason": "Names a place."}),
        )
        .await);

    let listing = |scope: &[(&str, &str)]| {
        let mut parameters = vec![("dataset_id", id(&dataset))];
        parameters.extend_from_slice(scope);
        format!("{RUNS}?{}", query(&parameters))
    };
    // No one case is both a node and named for the agent.
    let impossible = ok(studio
        .get(&listing(&[
            ("target_kind", "node"),
            ("evaluation_name", "Agent place realism"),
        ]))
        .await);
    assert_eq!(impossible["items"], json!([]));

    let node_scope = ok(studio
        .get(&listing(&[
            ("target_kind", "node"),
            ("target_key", "date_response_node"),
            ("input_version", "1"),
            ("evaluation_name", "Node place realism"),
        ]))
        .await);
    let node_run = &node_scope["items"][0];
    assert_eq!(
        node_run["outcome_summary"],
        json!({
            "total": 1,
            "queued": 1,
            "judged": 0,
            "passed": 0,
            "failed": 0,
            "error": 0,
            "pass_rate": null,
            "coverage": 0.0,
        })
    );
    // Facets describe the whole dataset whatever the scope, in name order.
    assert_eq!(
        node_run["target_facets"],
        json!([
            {
                "target_kind": "agent",
                "target_key": "chat_agent",
                "target_name": "AI Chat Agent",
                "input_version": 1,
                "case_count": 1,
            },
            {
                "target_kind": "agent",
                "target_key": "chat_agent",
                "target_name": "AI Chat Agent",
                "input_version": 2,
                "case_count": 1,
            },
            {
                "target_kind": "node",
                "target_key": "date_response_node",
                "target_name": "CreateDateIdeaResponseNode",
                "input_version": 1,
                "case_count": 1,
            },
        ])
    );
    assert_eq!(
        node_run["evaluation_facets"],
        json!([
            {"evaluation_name": "Agent place realism", "case_count": 2},
            {"evaluation_name": "Node place realism", "case_count": 1},
        ])
    );

    // Each filter narrows the counted attempts on its own.
    for (scope, total, passed, pass_rate) in [
        (vec![("target_kind", "agent")], 2, 1, json!(1.0)),
        (vec![("target_key", "chat_agent")], 2, 1, json!(1.0)),
        (vec![("input_version", "2")], 1, 0, Value::Null),
        (
            vec![("evaluation_name", "Agent place realism")],
            2,
            1,
            json!(1.0),
        ),
        (vec![], 3, 1, json!(1.0)),
    ] {
        let listed = ok(studio.get(&listing(&scope)).await);
        let summary = &listed["items"][0]["outcome_summary"];
        assert_eq!(summary["total"], total, "{scope:?}");
        assert_eq!(summary["passed"], passed, "{scope:?}");
        assert_eq!(summary["pass_rate"], pass_rate, "{scope:?}");
        assert_eq!(
            listed["items"][0]["target_facets"]
                .as_array()
                .unwrap()
                .len(),
            3
        );
    }
    let all = ok(studio.get(&listing(&[])).await);
    assert_eq!(
        all["items"][0]["outcome_summary"]["coverage"],
        json!(1.0 / 3.0)
    );

    for (parameters, rule) in [
        ("target_kind=tool", "unknown variant `tool`"),
        (
            "input_version=0",
            "version must be between 1 and 2147483647",
        ),
        ("input_version=one", "invalid digit"),
        ("target_key=", "key must not be blank"),
        (
            "evaluation_name=%20padded",
            "name must not contain surrounding whitespace",
        ),
        ("dataset_id=", "record ID must be 1 to 64 characters"),
    ] {
        let reply = studio.get(&format!("{RUNS}?{parameters}")).await;
        let message = invalid(&reply, parameters);
        assert!(message.contains(rule), "{parameters}: {message}");
    }
}

#[tokio::test]
async fn missing_records_are_not_found() {
    let studio = Studio::new().await;
    for (reply, message) in [
        (
            studio.get(&format!("{DATASETS}/missing")).await,
            "Dataset not found",
        ),
        (
            studio
                .add_case("missing", case_body("specific_place_1"))
                .await,
            "Dataset not found",
        ),
        (
            studio.put(&format!("{DATASETS}/missing/lock"), None).await,
            "Dataset not found",
        ),
        (
            studio.start_run("missing", "baseline").await,
            "Dataset not found",
        ),
        (
            studio.get(&format!("{RUNS}/missing")).await,
            "Run not found",
        ),
        (
            studio.get(&format!("{ATTEMPTS}/missing")).await,
            "Attempt not found",
        ),
        (
            studio.bind("missing", &execution("workflow-run")).await,
            "Attempt not found",
        ),
        (
            studio
                .record(
                    "missing",
                    json!({"status": "error", "reason": "Setup failed."}),
                )
                .await,
            "Attempt not found",
        ),
    ] {
        assert_not_found(&reply, message);
    }
    // A listing scoped to a dataset that does not exist is empty.
    let listed = ok(studio.get(&format!("{RUNS}?dataset_id=missing")).await);
    assert_eq!(listed["items"], json!([]));
}

#[tokio::test]
async fn adding_a_case_and_locking_share_one_write_boundary() {
    let studio = Studio::new().await;
    // The two requests race in both submission orders.
    for add_first in [true, false] {
        let dataset = studio
            .create_dataset(&format!("race_dataset_{add_first}"))
            .await;
        let lock_uri = format!("{DATASETS}/{}/lock", id(&dataset));
        let add = studio.add_case(id(&dataset), case_body("racing_case"));
        let lock = studio.put(&lock_uri, None);
        let (added, locked) = if add_first {
            tokio::join!(add, lock)
        } else {
            let (locked, added) = tokio::join!(lock, add);
            (added, locked)
        };

        assert_eq!(ok(locked)["status"], "locked");
        // The case was added before the lock, or refused after it.
        let case_count = match added.status {
            StatusCode::OK => 1,
            _ => {
                assert_conflict(
                    &added,
                    "dataset_locked",
                    "Locked datasets cannot accept new cases.",
                );
                0
            }
        };
        let detail = studio.dataset_detail(id(&dataset)).await;
        assert_eq!(detail["dataset"]["status"], "locked");
        assert_eq!(detail["cases"].as_array().unwrap().len(), case_count);
    }
}

#[tokio::test]
async fn concurrent_final_results_complete_the_run_once() {
    let studio = Studio::new().await;
    let (_dataset, run) = studio
        .locked_dataset_with_run("race_dataset", &["case_1", "case_2"])
        .await;
    let attempts = each(&run["cases"], "/attempt/id");
    for (ordinal, attempt_id) in attempts.iter().enumerate() {
        let evidence = execution(&format!("workflow-run-{ordinal}"));
        ok(studio.bind(attempt_id.as_str().unwrap(), &evidence).await);
    }

    let result = json!({
        "status": "passed",
        "reason": "The response names a specific plausible place.",
    });
    let (first, second) = tokio::join!(
        studio.record(attempts[0].as_str().unwrap(), result.clone()),
        studio.record(attempts[1].as_str().unwrap(), result.clone()),
    );
    ok(first);
    ok(second);

    let completed = studio.run_detail(id(&run["run"])).await;
    assert_eq!(completed["run"]["status"], "completed");
    assert!(completed["run"]["completed_at"].is_string());
    assert_eq!(
        each(&completed["cases"], "/attempt/status"),
        [&json!("passed"), &json!("passed")]
    );
}

#[tokio::test]
async fn one_execution_is_the_subject_of_one_attempt() {
    let studio = Studio::new().await;
    let (_dataset, run) = studio
        .locked_dataset_with_run("race_dataset", &["case_1", "case_2"])
        .await;
    let attempts = each(&run["cases"], "/attempt/id");
    let evidence = execution("one-runtime-id");

    let (first, second) = tokio::join!(
        studio.bind(attempts[0].as_str().unwrap(), &evidence),
        studio.bind(attempts[1].as_str().unwrap(), &evidence),
    );
    let (bound, refused) = match first.status {
        StatusCode::OK => (first, second),
        _ => (second, first),
    };
    assert_eq!(ok(bound)["subject_evidence"], evidence);
    assert_conflict(
        &refused,
        "evidence_already_bound",
        "Evidence is already bound to another attempt.",
    );

    // The refused attempt is unchanged and can take other evidence. The
    // same rule holds for a span.
    let detail = studio.run_detail(id(&run["run"])).await;
    let unbound: Vec<&Value> = detail["cases"]
        .as_array()
        .unwrap()
        .iter()
        .map(|case| &case["attempt"])
        .filter(|attempt| attempt["subject_evidence"].is_null())
        .collect();
    assert_eq!(unbound.len(), 1);
    assert_eq!(unbound[0]["evidence_bound_at"], Value::Null);
    let free_span = span(&"1".repeat(32), &"a".repeat(16));
    ok(studio.bind(id(unbound[0]), &free_span).await);

    let (_other_dataset, other_run) = studio
        .locked_dataset_with_run("other_dataset", &["case_1"])
        .await;
    let other_attempt = id(&other_run["cases"][0]["attempt"]);
    for taken in [&evidence, &free_span] {
        assert_conflict(
            &studio.bind(other_attempt, taken).await,
            "evidence_already_bound",
            "Evidence is already bound to another attempt.",
        );
    }
    // Evidence that is a subject may still be the source of cases.
    let draft = studio.create_dataset("generated_from_subject").await;
    ok(studio
        .add_case(id(&draft), generated_case_body("case_1", &evidence))
        .await);
}

#[tokio::test]
async fn concurrent_identical_requests_create_one_record() {
    let studio = Studio::new().await;
    let (first, second) = tokio::join!(
        studio.post(DATASETS, dataset_body("race_dataset")),
        studio.post(DATASETS, dataset_body("race_dataset")),
    );
    let dataset = ok(first);
    assert_eq!(ok(second), dataset);
    let listed = ok(studio.get(DATASETS).await);
    assert_eq!(listed["items"], json!([dataset]));

    let (first, second, other) = tokio::join!(
        studio.add_case(id(&dataset), case_body("racing_case")),
        studio.add_case(id(&dataset), case_body("racing_case")),
        studio.add_case(id(&dataset), case_body("other_case")),
    );
    let case = ok(first);
    assert_eq!(ok(second), case);
    let other = ok(other);
    let mut ordinals = [case["ordinal"].as_i64(), other["ordinal"].as_i64()];
    ordinals.sort();
    assert_eq!(ordinals, [Some(1), Some(2)]);

    studio.lock(id(&dataset)).await;
    let (first, second) = tokio::join!(
        studio.start_run(id(&dataset), "racing-request"),
        studio.start_run(id(&dataset), "racing-request"),
    );
    let run = ok(first);
    assert_eq!(ok(second), run);
    assert_eq!(run["cases"].as_array().unwrap().len(), 2);
    let listed = ok(studio.get(RUNS).await);
    assert_eq!(each(&listed["items"], "/run/id"), [&run["run"]["id"]]);
    assert_eq!(listed["items"][0]["outcome_summary"]["total"], 2);
}

#[tokio::test]
async fn every_read_of_a_record_returns_the_same_record() {
    let studio = Studio::new().await;
    let source = span(&"2".repeat(32), &"b".repeat(16));
    let dataset = studio.create_dataset("one_record").await;
    let authored = ok(studio.add_case(id(&dataset), case_body("authored")).await);
    let generated = ok(studio
        .add_case(id(&dataset), generated_case_body("generated", &source))
        .await);
    let dataset = studio.lock(id(&dataset)).await;
    let started = ok(studio.start_run(id(&dataset), "baseline-request").await);
    let attempt_id = id(&started["cases"][1]["attempt"]);
    ok(studio.bind(attempt_id, &execution("workflow-run")).await);
    let attempt = ok(studio
        .record(
            attempt_id,
            json!({"status": "failed", "reason": "No place named.", "duration_ms": 1200}),
        )
        .await);

    let detail = studio.dataset_detail(id(&dataset)).await;
    assert_eq!(
        detail,
        json!({"dataset": dataset, "cases": [authored, generated]})
    );
    let listed = ok(studio.get(DATASETS).await);
    assert_eq!(listed["items"], json!([dataset]));

    let run = studio.run_detail(id(&started["run"])).await;
    assert_eq!(run["dataset"], dataset);
    assert_eq!(each(&run["cases"], "/case"), [&authored, &generated]);
    assert_eq!(run["cases"][1]["attempt"], attempt);
    let runs = ok(studio.get(RUNS).await);
    assert_eq!(runs["items"][0]["run"], run["run"]);

    let attempt_detail = ok(studio.get(&format!("{ATTEMPTS}/{attempt_id}")).await);
    assert_eq!(
        attempt_detail,
        json!({
            "run": run["run"],
            "dataset": dataset,
            "case": generated,
            "attempt": attempt,
        })
    );
}
