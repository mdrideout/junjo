use axum::http::{Method, StatusCode};
use serde_json::{Value, json};

use super::*;
use crate::test_http::{app, get as http_get, post, send, sign_up, with_authorization};
use crate::test_support::TestSpan;

const TRACE_ID: &str = "11111111111111111111111111111111";
const SPAN_ID: &str = "aaaaaaaaaaaaaaaa";
const NODE_SPAN_ID: &str = "bbbbbbbbbbbbbbbb";
const AGENT_SPAN_ID: &str = "cccccccccccccccc";

fn identity(executable_type: ExecutableType) -> ExecutionIdentity {
    ExecutionIdentity {
        service_namespace: "junjo.examples".to_string(),
        service_name: "ai-chat".to_string(),
        executable_type,
        runtime_id: "workflow-run".to_string(),
    }
}

fn span(span_id: &str, parent_span_id: Option<&str>, attributes: Value) -> NormalizedSpanEvidence {
    serde_json::from_value(json!({
        "trace_id": TRACE_ID,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "service_name": "ai-chat",
        "name": "span",
        "kind": "INTERNAL",
        "start_time": "2025-01-15T10:30:00.000000+00:00",
        "end_time": "2025-01-15T10:30:01.000000+00:00",
        "status_code": "0",
        "status_message": "",
        "attributes_json": attributes,
        "events_json": [],
        "links_json": [],
        "trace_flags": 0,
        "trace_state": null,
        "dropped_attributes_count": 0,
        "dropped_events_count": 0,
        "dropped_links_count": 0,
        "resource_attributes_json": {
            "service.namespace": "junjo.examples",
            "service.name": "ai-chat",
        },
        "resource_dropped_attributes_count": 0,
    }))
    .unwrap()
}

fn owner_attributes(executable_type: &str, runtime_id: &str) -> Value {
    json!({
        "junjo.telemetry.contract_version": 3,
        "junjo.span_type": executable_type,
        "junjo.executable_runtime_id": runtime_id,
    })
}

fn owner(executable_type: &str) -> NormalizedSpanEvidence {
    span(
        SPAN_ID,
        None,
        owner_attributes(executable_type, "workflow-run"),
    )
}

fn node(span_id: &str, parent_span_id: &str, attributes: Value) -> NormalizedSpanEvidence {
    let mut attributes = attributes;
    attributes["junjo.telemetry.contract_version"] = json!(3);
    span(span_id, Some(parent_span_id), attributes)
}

#[test]
fn an_owner_resolves_to_the_pages_that_show_it() {
    for (executable_type, name, detail) in [
        (
            ExecutableType::Workflow,
            "workflow",
            format!("/workflows/ai-chat/{TRACE_ID}/{SPAN_ID}"),
        ),
        (
            ExecutableType::Subflow,
            "subflow",
            format!("/workflows/ai-chat/{TRACE_ID}/{SPAN_ID}"),
        ),
        (
            ExecutableType::Agent,
            "agent",
            format!("/agents/{TRACE_ID}/{SPAN_ID}"),
        ),
    ] {
        let identity = identity(executable_type);
        let candidates = [owner(name)];
        let owners = owners(&candidates, &identity);
        assert_eq!(owners.len(), 1, "{name}");
        let resolved = resolution(&identity, owners[0], None, None);
        assert_eq!(resolved.detail_path, detail);
        assert_eq!(resolved.failure_path, detail);
        assert_eq!(
            resolved.trace_path,
            format!("/traces/ai-chat/{TRACE_ID}/{SPAN_ID}")
        );
    }
}

#[test]
fn the_service_name_is_one_encoded_path_segment() {
    let mut identity = identity(ExecutableType::Workflow);
    identity.service_name = "team/ai chat".to_string();
    let resolved = resolution(&identity, &owner("workflow"), None, None);
    assert_eq!(
        resolved.detail_path,
        format!("/workflows/team%2Fai%20chat/{TRACE_ID}/{SPAN_ID}")
    );
    assert_eq!(
        resolved.trace_path,
        format!("/traces/team%2Fai%20chat/{TRACE_ID}/{SPAN_ID}")
    );
}

#[test]
fn candidates_are_filtered_by_the_complete_identity() {
    let identity = identity(ExecutableType::Workflow);
    let mut wrong_namespace = owner("workflow");
    wrong_namespace
        .resource_attributes_json
        .insert("service.namespace".to_string(), json!("wrong"));
    let mut wrong_service = owner("workflow");
    wrong_service
        .resource_attributes_json
        .insert("service.name".to_string(), json!("wrong"));
    let wrong_runtime = span(SPAN_ID, None, owner_attributes("workflow", "wrong"));
    let wrong_type = owner("agent");
    let mut old_contract = owner("workflow");
    old_contract
        .attributes_json
        .insert("junjo.telemetry.contract_version".to_string(), json!(1));
    let mut no_namespace = owner("workflow");
    no_namespace
        .resource_attributes_json
        .shift_remove("service.namespace");

    let candidates = [
        wrong_namespace,
        wrong_service,
        wrong_runtime,
        wrong_type,
        old_contract,
        no_namespace.clone(),
    ];
    assert!(owners(&candidates, &identity).is_empty());

    // A service without a namespace is found by the empty namespace only.
    let mut empty_namespace = identity.clone();
    empty_namespace.service_namespace = String::new();
    assert_eq!(owners(&[no_namespace], &empty_namespace).len(), 1);
}

#[test]
fn the_real_node_of_a_one_node_workflow_is_selected() {
    let mut owner = owner("workflow");
    let snapshot = json!({
        "v": 2,
        "nodes": [{
            "nodeRuntimeId": "node-runtime",
            "nodeStructuralId": "node-structural-id",
            "nodeLabel": "CreateDateIdeaResponseNode",
            "nodeType": "CreateDateIdeaResponseNode",
        }],
        "edges": [],
        "graphStructuralId": "graph-structural-id",
    });
    // Producers send the snapshot as JSON text.
    owner.attributes_json.insert(
        "junjo.workflow.execution_graph_snapshot".to_string(),
        json!(snapshot.to_string()),
    );
    let node_attributes = json!({
        "junjo.span_type": "node",
        "junjo.executable_runtime_id": "node-runtime",
    });
    let trace = [
        owner.clone(),
        node(NODE_SPAN_ID, SPAN_ID, node_attributes.clone()),
    ];

    let runtime_id = single_graph_node_runtime_id(&owner).unwrap();
    assert_eq!(runtime_id, "node-runtime");
    assert_eq!(
        single_graph_node_span_id(&owner, &runtime_id, &trace).as_deref(),
        Some(NODE_SPAN_ID)
    );

    // Two spans claiming the Node's identity select nothing.
    let doubled = [
        node(NODE_SPAN_ID, SPAN_ID, node_attributes.clone()),
        node(AGENT_SPAN_ID, SPAN_ID, node_attributes.clone()),
    ];
    assert_eq!(
        single_graph_node_span_id(&owner, &runtime_id, &doubled),
        None
    );
    // A Node elsewhere in the trace is not this Workflow's Node.
    let elsewhere = [node(NODE_SPAN_ID, AGENT_SPAN_ID, node_attributes)];
    assert_eq!(
        single_graph_node_span_id(&owner, &runtime_id, &elsewhere),
        None
    );

    // A graph with any other number of Nodes selects nothing.
    let mut two_nodes = owner.clone();
    two_nodes.attributes_json.insert(
        "junjo.workflow.execution_graph_snapshot".to_string(),
        json!({
            "nodes": [{"nodeRuntimeId": "a"}, {"nodeRuntimeId": "b"}],
        }),
    );
    assert_eq!(single_graph_node_runtime_id(&two_nodes), None);
    let mut unreadable = owner.clone();
    unreadable.attributes_json.insert(
        "junjo.workflow.execution_graph_snapshot".to_string(),
        json!("{not json"),
    );
    assert_eq!(single_graph_node_runtime_id(&unreadable), None);
}

#[test]
fn the_single_failed_node_inside_a_workflow_is_selected() {
    let mut owner = owner("workflow");
    owner
        .attributes_json
        .insert("error.type".to_string(), json!("AgentError"));
    assert!(has_failure_signal(&owner));

    let mut failed_node = node(
        NODE_SPAN_ID,
        SPAN_ID,
        json!({"junjo.span_type": "node", "error.type": "AgentError"}),
    );
    failed_node.events_json = vec![json!({"name": "exception"})];
    // The failed Agent inside the Node is not a Node.
    let failed_agent = node(
        AGENT_SPAN_ID,
        NODE_SPAN_ID,
        json!({"junjo.span_type": "agent", "error.type": "AgentError"}),
    );
    let trace = [owner.clone(), failed_node.clone(), failed_agent];
    assert_eq!(
        single_failed_node_span_id(&owner, &trace).as_deref(),
        Some(NODE_SPAN_ID)
    );

    // A second failed Node, however deep, selects nothing.
    let mut nested = node(
        "dddddddddddddddd",
        AGENT_SPAN_ID,
        json!({"junjo.span_type": "node"}),
    );
    nested.events_json = vec![json!({"name": "junjo.hook_error"})];
    let mut two_failed = trace.to_vec();
    two_failed.push(nested);
    assert_eq!(single_failed_node_span_id(&owner, &two_failed), None);

    // A failed Node outside the Workflow is not its failure.
    let mut outside = failed_node;
    outside.parent_span_id = Some("eeeeeeeeeeeeeeee".to_string());
    assert_eq!(single_failed_node_span_id(&owner, &[outside]), None);
}

#[test]
fn a_parent_cycle_ends_the_ancestor_walk() {
    let first = node(
        NODE_SPAN_ID,
        AGENT_SPAN_ID,
        json!({"junjo.span_type": "node"}),
    );
    let second = node(
        AGENT_SPAN_ID,
        NODE_SPAN_ID,
        json!({"junjo.span_type": "node"}),
    );
    let trace = [first.clone(), second];
    let parents: HashMap<&str, Option<&str>> = trace
        .iter()
        .map(|span| (span.span_id.as_str(), span.parent_span_id.as_deref()))
        .collect();
    assert!(!is_descendant(&first, SPAN_ID, &parents));
}

fn stored_span(span_id: &str, attributes: Value) -> TestSpan {
    TestSpan {
        resource_attributes: json!({
            "service.namespace": "junjo.examples",
            "service.name": "ai-chat",
        })
        .to_string(),
        ..TestSpan::new(TRACE_ID, span_id, "ai-chat")
    }
    .attributes(&attributes.to_string())
}

const QUERY: &str = "/api/v1/execution-resolution?service_namespace=junjo.examples\
                     &service_name=ai-chat&executable_type=workflow&runtime_id=workflow-run";

#[tokio::test]
async fn the_route_needs_a_session_or_an_evidence_token() {
    let (router, _app) = app();
    let anonymous = send(&router, http_get(QUERY, None)).await;
    assert_eq!(anonymous.status, StatusCode::UNAUTHORIZED);

    let cookie = sign_up(&router).await;
    let mut tokens = Vec::new();
    for scope in ["evidence:read", "evaluation:read"] {
        let created = send(
            &router,
            post(
                "/api/v1/evaluation-tokens",
                Some(&cookie),
                json!({"name": scope, "scopes": [scope]}),
            ),
        )
        .await;
        tokens.push(format!(
            "Bearer {}",
            created.body["token"].as_str().unwrap()
        ));
    }
    let with_scope = send(
        &router,
        with_authorization(Method::GET, QUERY, &tokens[0], None),
    )
    .await;
    assert_eq!(with_scope.status, StatusCode::NOT_FOUND);
    let without_scope = send(
        &router,
        with_authorization(Method::GET, QUERY, &tokens[1], None),
    )
    .await;
    assert_eq!(without_scope.status, StatusCode::FORBIDDEN);
    assert_eq!(
        without_scope.body["missing_scopes"],
        json!(["evidence:read"])
    );
}

#[tokio::test]
async fn a_stored_owner_span_resolves_through_the_route() {
    let (router, mut app) = app();
    let cookie = sign_up(&router).await;

    let missing = send(&router, http_get(QUERY, Some(&cookie))).await;
    assert_eq!(missing.status, StatusCode::NOT_FOUND);
    assert_eq!(
        missing.body,
        json!({"code": "not_found", "message": "Execution not found"})
    );

    let mut owner_attributes = owner_attributes("workflow", "workflow-run");
    owner_attributes["junjo.workflow.execution_graph_snapshot"] =
        json!(json!({"nodes": [{"nodeRuntimeId": "node-runtime"}]}).to_string());
    app.index_cold_file(
        "workflow.parquet",
        &[
            stored_span(SPAN_ID, owner_attributes),
            stored_span(
                NODE_SPAN_ID,
                json!({
                    "junjo.telemetry.contract_version": 3,
                    "junjo.span_type": "node",
                    "junjo.executable_runtime_id": "node-runtime",
                }),
            )
            .parent(SPAN_ID),
        ],
    );

    let resolved = send(&router, http_get(QUERY, Some(&cookie))).await;
    assert_eq!(resolved.status, StatusCode::OK, "{}", resolved.body);
    assert_eq!(
        resolved.body,
        json!({
            "service_namespace": "junjo.examples",
            "service_name": "ai-chat",
            "executable_type": "workflow",
            "runtime_id": "workflow-run",
            "trace_id": TRACE_ID,
            "span_id": SPAN_ID,
            "detail_path": format!("/workflows/ai-chat/{TRACE_ID}/{SPAN_ID}/{NODE_SPAN_ID}"),
            "failure_path": format!("/workflows/ai-chat/{TRACE_ID}/{SPAN_ID}"),
            "trace_path": format!("/traces/ai-chat/{TRACE_ID}/{SPAN_ID}"),
        })
    );

    // The same identity in another namespace is another execution.
    let other_namespace = send(
        &router,
        http_get(
            &QUERY.replace("junjo.examples", "junjo.other"),
            Some(&cookie),
        ),
    )
    .await;
    assert_eq!(other_namespace.status, StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn two_owner_spans_with_one_identity_are_a_conflict() {
    let (router, mut app) = app();
    let cookie = sign_up(&router).await;
    app.index_cold_file(
        "duplicated.parquet",
        &[
            stored_span(SPAN_ID, owner_attributes("workflow", "workflow-run")),
            stored_span(NODE_SPAN_ID, owner_attributes("workflow", "workflow-run")),
        ],
    );

    let conflict = send(&router, http_get(QUERY, Some(&cookie))).await;
    assert_eq!(conflict.status, StatusCode::CONFLICT);
    assert_eq!(
        conflict.body,
        json!({
            "code": "ambiguous_execution_identity",
            "message": "Execution identity resolved to multiple owner spans.",
            "match_count": 2,
        })
    );
}

#[tokio::test]
async fn an_incomplete_identity_is_refused() {
    let (router, _app) = app();
    let cookie = sign_up(&router).await;
    for query in [
        // The namespace is required; an empty one must be stated.
        "service_name=ai-chat&executable_type=workflow&runtime_id=run",
        "service_namespace=&service_name=&executable_type=workflow&runtime_id=run",
        "service_namespace=&service_name=ai-chat&executable_type=node&runtime_id=run",
        "service_namespace=&service_name=ai-chat&executable_type=workflow&runtime_id=",
        "service_namespace=&service_name=ai-chat&executable_type=workflow&runtime_id=run&extra=1",
    ] {
        let reply = send(
            &router,
            http_get(
                &format!("/api/v1/execution-resolution?{query}"),
                Some(&cookie),
            ),
        )
        .await;
        assert_eq!(reply.status, StatusCode::UNPROCESSABLE_ENTITY, "{query}");
        assert_eq!(reply.body["code"], "invalid_request", "{query}");
    }
    let empty_namespace = send(
        &router,
        http_get(
            "/api/v1/execution-resolution?service_namespace=&service_name=ai-chat\
             &executable_type=agent&runtime_id=run",
            Some(&cookie),
        ),
    )
    .await;
    assert_eq!(empty_namespace.status, StatusCode::NOT_FOUND);
}
