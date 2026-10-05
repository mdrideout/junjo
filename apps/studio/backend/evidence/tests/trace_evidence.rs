//! Contract tests for cohesive trace evidence.

mod common;

use std::collections::BTreeSet;

use junjo_evidence::agent_diagnostics::schemas::AgentOperation;
use junjo_evidence::json::Json;
use junjo_evidence::store_diagnostics::schemas::ReconstructionStatus;
use junjo_evidence::trace_evidence::assembler::{
    assemble_attempt_evidence_manifest, assemble_trace_evidence, select_attempt_span_evidence,
};
use junjo_evidence::trace_evidence::schemas::{
    AttemptManifest, ExecutableAnnotation, NormalizedSpanEvidence, OperationType, SemanticSpanKind,
    StoreRole, TraceEvidence,
};
use serde_json::json;

const RAW_SPAN_FIELDS: [&str; 20] = [
    "trace_id",
    "span_id",
    "parent_span_id",
    "service_name",
    "name",
    "kind",
    "start_time",
    "end_time",
    "status_code",
    "status_message",
    "attributes_json",
    "events_json",
    "links_json",
    "trace_flags",
    "trace_state",
    "dropped_attributes_count",
    "dropped_events_count",
    "dropped_links_count",
    "resource_attributes_json",
    "resource_dropped_attributes_count",
];

/// The raw spans of one fixture, as stored JSON.
fn raw_spans(relative: &str) -> Vec<Json> {
    let fixture = common::read_json(&common::fixture_root().join(relative));
    fixture["spans"].as_array().unwrap().clone()
}

fn typed(spans: &[Json]) -> Vec<NormalizedSpanEvidence> {
    spans
        .iter()
        .map(|span| serde_json::from_value(span.clone()).expect("a normalized span"))
        .collect()
}

fn evidence(spans: &[Json]) -> TraceEvidence {
    assemble_trace_evidence(spans[0]["trace_id"].as_str().unwrap(), typed(spans))
}

fn nested_workflow_fixture() -> Vec<Json> {
    raw_spans("agent/producer/tool_invokes_nested_workflow.json")
}

fn failure_fixture() -> Vec<Json> {
    raw_spans("agent/producer/multi_tool_first_failure.json")
}

fn span_of_type<'a>(spans: &'a mut [Json], span_type: &str) -> &'a mut Json {
    spans
        .iter_mut()
        .find(|span| span["attributes_json"]["junjo.span_type"] == span_type)
        .unwrap_or_else(|| panic!("a {span_type} span"))
}

/// A manifest for the Attempt subject `owner` would resolve to.
fn manifest(evidence: &TraceEvidence, owner: &Json) -> AttemptManifest {
    let service_name = owner["resource_attributes_json"]["service.name"]
        .as_str()
        .unwrap();
    assemble_attempt_evidence_manifest(service_name, evidence)
}

#[test]
fn trace_evidence_is_lossless_and_indexes_independent_owners() {
    let spans = nested_workflow_fixture();

    let evidence = evidence(&spans);

    assert_eq!(evidence.spans.len(), spans.len());
    assert_eq!(
        serde_json::to_value(&evidence.spans).unwrap(),
        Json::Array(spans.clone())
    );
    for span in &evidence.spans {
        let object = span.to_object();
        let fields: Vec<&str> = object.keys().map(String::as_str).collect();
        assert_eq!(fields, RAW_SPAN_FIELDS);
    }

    let agent = evidence
        .executables_by_span_id
        .values()
        .find_map(|executable| match executable {
            ExecutableAnnotation::Agent(agent) => Some(agent),
            ExecutableAnnotation::Workflow(_) => None,
        })
        .expect("an Agent annotation");
    assert_eq!(agent.owner_span_id, agent.summary.agent_span_id);
    let operations: BTreeSet<&str> = evidence.operations_by_owner_runtime_id[&agent.runtime_id]
        .keys()
        .map(String::as_str)
        .collect();
    let expected: BTreeSet<&str> = spans
        .iter()
        .filter(|span| {
            let attributes = &span["attributes_json"];
            attributes["junjo.agent.runtime_id"] == agent.runtime_id.as_str()
                && matches!(
                    attributes["junjo.agent.operation_type"].as_str(),
                    Some("model_request" | "tool")
                )
        })
        .map(|span| span["span_id"].as_str().unwrap())
        .collect();
    assert_eq!(operations, expected);
    let runtime_store_id = agent.stores[&StoreRole::Runtime]
        .store_id
        .as_ref()
        .expect("an Agent runtime Store");
    assert!(evidence.stores_by_id.contains_key(runtime_store_id));
    assert!(!agent.stores[&StoreRole::Application].available);
    assert!(
        !evidence.relationships_by_owner_span_id[&agent.owner_span_id]
            .nested
            .is_empty()
    );
}

#[test]
fn a_span_with_an_unknown_field_is_not_a_normalized_span() {
    let mut span = nested_workflow_fixture().remove(0);
    span["duration_ns"] = json!(1);
    assert!(serde_json::from_value::<NormalizedSpanEvidence>(span).is_err());
}

#[test]
fn trace_evidence_preserves_raw_span_when_annotation_is_unsupported() {
    let mut spans = nested_workflow_fixture();
    let owner = span_of_type(&mut spans, "agent");
    owner["attributes_json"]["junjo.telemetry.contract_version"] = json!(999);
    let owner_span_id = owner["span_id"].as_str().unwrap().to_string();

    let evidence = evidence(&spans);

    assert_eq!(evidence.spans.len(), spans.len());
    assert!(!evidence.executables_by_span_id.contains_key(&owner_span_id));
    assert!(evidence.diagnostics.iter().any(|diagnostic| {
        diagnostic.owner_span_id.as_ref() == Some(&owner_span_id)
            && diagnostic.issue.code == "unsupported_contract"
    }));
}

#[test]
fn attempt_manifest_is_payload_light_and_projects_every_failure() {
    let spans = failure_fixture();
    let evidence = evidence(&spans);

    let manifest = manifest(&evidence, &spans[0]);

    let span_ids = |indexes: &[usize]| -> Vec<&str> {
        indexes
            .iter()
            .map(|index| spans[*index]["span_id"].as_str().unwrap())
            .collect()
    };
    let all: Vec<usize> = (0..spans.len()).collect();
    assert_eq!(manifest.trace.span_count, spans.len());
    assert_eq!(manifest.trace.root_span_ids, span_ids(&[0]));
    let listed: Vec<&str> = manifest
        .spans
        .iter()
        .map(|entry| entry.span_id.as_str())
        .collect();
    assert_eq!(listed, span_ids(&all));
    let rendered = serde_json::to_value(&manifest).unwrap();
    assert!(rendered["spans"][0].get("attributes_json").is_none());
    assert!(rendered["operations"][0].get("request").is_none());
    assert!(rendered["stores"][0].get("transitions").is_none());

    let failed: Vec<&str> = manifest
        .failures
        .iter()
        .map(|failure| failure.span_id.as_str())
        .collect();
    assert_eq!(failed, span_ids(&[0, 2]));
    let owner = spans[0]["span_id"].as_str();
    for failure in &manifest.failures {
        assert!(failure.stacktrace_available);
        assert!(!failure.start_time.is_empty() && !failure.end_time.is_empty());
        assert_eq!(failure.owner_span_id.as_deref(), owner);
        assert_eq!(failure.owner_runtime_id, manifest.executables[0].runtime_id);
    }
    assert_eq!(
        manifest.failures[1].exception_type.as_deref(),
        Some("junjo.agent.errors.AgentToolError")
    );
    assert_eq!(
        manifest.failures[1].exception_message.as_deref(),
        Some("Tool 'lookup' service failed.")
    );
    assert_eq!(manifest.operations.len(), 2);
    assert_eq!(manifest.stores[0].transition_count, 5);
}

#[test]
fn attempt_manifest_summarizes_openinference_and_gen_ai_operations() {
    let mut template = nested_workflow_fixture().remove(0);
    for (key, value) in [
        ("span_id", json!("1111111111111111")),
        ("parent_span_id", Json::Null),
        ("name", json!("evaluation attempt")),
        ("attributes_json", json!({})),
        ("events_json", json!([])),
        ("links_json", json!([])),
        ("status_code", json!("1")),
        ("status_message", json!("")),
    ] {
        template[key] = value;
    }
    let mut openinference_model = template.clone();
    openinference_model["span_id"] = json!("2222222222222222");
    openinference_model["parent_span_id"] = template["span_id"].clone();
    openinference_model["name"] = json!("AsyncGenerateContent");
    openinference_model["attributes_json"] = json!({
        "openinference.span.kind": "LLM",
        "llm.model_name": "gemini-3.7-flash",
    });
    let mut gen_ai_tool = template.clone();
    gen_ai_tool["span_id"] = json!("3333333333333333");
    gen_ai_tool["parent_span_id"] = template["span_id"].clone();
    gen_ai_tool["name"] = json!("execute_tool lookup");
    gen_ai_tool["attributes_json"] = json!({
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": "lookup",
    });
    let spans = [template, openinference_model, gen_ai_tool];
    let evidence = evidence(&spans);

    let manifest = manifest(&evidence, &spans[0]);

    let kinds: Vec<SemanticSpanKind> = manifest
        .spans
        .iter()
        .map(|span| span.semantic_kind)
        .collect();
    assert_eq!(
        kinds,
        [
            SemanticSpanKind::Span,
            SemanticSpanKind::Model,
            SemanticSpanKind::Tool
        ]
    );
    let operations: Vec<(&str, &str, OperationType)> = manifest
        .operations
        .iter()
        .map(|operation| {
            (
                operation.span_id.as_str(),
                operation.name.as_str(),
                operation.operation_type,
            )
        })
        .collect();
    assert_eq!(
        operations,
        [
            (
                "2222222222222222",
                "gemini-3.7-flash",
                OperationType::ModelRequest
            ),
            ("3333333333333333", "lookup", OperationType::Tool),
        ]
    );
    for operation in &manifest.operations {
        assert_eq!(operation.owner_span_id, None);
        assert_eq!(operation.owner_runtime_id, None);
        assert_eq!(operation.duration_ns, None);
    }
}

#[test]
fn attempt_manifest_preserves_hook_and_status_failure_messages() {
    let mut spans = raw_spans("workflow/hook_failure_on_surrounding_span.json");
    let hook = spans
        .iter()
        .position(|span| {
            span["events_json"]
                .as_array()
                .unwrap()
                .iter()
                .any(|event| event["name"] == "junjo.hook_error")
        })
        .expect("a span with a hook error");
    let hook_attributes = spans[hook]["events_json"][0]["attributes"]
        .as_object_mut()
        .unwrap();
    hook_attributes.shift_remove("exception.type");
    hook_attributes.shift_remove("exception.message");
    let mut status_failure = spans[hook].clone();
    for (key, value) in [
        ("span_id", json!("7777777777777777")),
        ("name", json!("external model request")),
        ("status_code", json!("2")),
        ("status_message", json!("provider request failed")),
        ("attributes_json", json!({"openinference.span.kind": "LLM"})),
        ("events_json", json!([])),
    ] {
        status_failure[key] = value;
    }
    spans.push(status_failure);
    let evidence = evidence(&spans);

    let manifest = manifest(&evidence, &spans[0]);

    let failure = |span_id: &Json| {
        manifest
            .failures
            .iter()
            .find(|failure| failure.span_id == span_id.as_str().unwrap())
            .expect("a failure entry")
    };
    let hook_failure = failure(&spans[hook]["span_id"]);
    assert_eq!(hook_failure.exception_type.as_deref(), Some("RuntimeError"));
    assert_eq!(
        hook_failure.exception_message.as_deref(),
        Some("hook exploded")
    );
    assert!(hook_failure.stacktrace_available);
    assert_eq!(
        failure(&json!("7777777777777777"))
            .exception_message
            .as_deref(),
        Some("provider request failed")
    );
}

#[test]
fn selected_spans_preserve_order_and_direct_semantic_evidence() {
    let spans = failure_fixture();
    let evidence = evidence(&spans);
    let span_id = |index: usize| spans[index]["span_id"].as_str().unwrap().to_string();
    let missing_span_id = "f".repeat(16);

    let selected = select_attempt_span_evidence(
        &evidence,
        &[span_id(2), span_id(0), missing_span_id.clone()],
    );

    let returned: Vec<&str> = selected
        .items
        .iter()
        .map(|item| item.span.span_id.as_str())
        .collect();
    assert_eq!(returned, [span_id(2), span_id(0)]);
    assert_eq!(selected.missing_span_ids, [missing_span_id]);
    assert!(matches!(
        selected.items[0].operation,
        Some(AgentOperation::Tool(_))
    ));
    assert_eq!(selected.items[0].executable, None);
    assert!(selected.items[0].stores.is_empty());
    assert!(selected.items[1].executable.is_some());
    assert_eq!(selected.items[1].operation, None);
    assert_eq!(selected.items[1].stores[0].owner_span_id, span_id(0));
}

#[test]
fn attempt_manifest_reports_unavailable_store_integrity() {
    let spans = raw_spans("agent/producer/boundary_input_history_rejection.json");
    let evidence = evidence(&spans);

    let manifest = manifest(&evidence, &spans[0]);

    let unavailable: Vec<_> = manifest
        .stores
        .iter()
        .filter(|store| !store.available)
        .collect();
    assert!(!unavailable.is_empty());
    for store in unavailable {
        assert_eq!(store.store_id, None);
        assert_eq!(store.transition_count, 0);
        assert!(!store.reconstructable);
        assert_eq!(
            store.reconstruction_status,
            ReconstructionStatus::NotApplicable
        );
    }
}

#[test]
fn attempt_manifest_does_not_misattribute_duplicate_store_identity() {
    let mut spans = nested_workflow_fixture();
    let agent = span_of_type(&mut spans, "agent").clone();
    let workflow = span_of_type(&mut spans, "workflow");
    workflow["attributes_json"]["junjo.workflow.store.id"] =
        agent["attributes_json"]["junjo.agent.store.id"].clone();
    let workflow_span_id = workflow["span_id"].as_str().unwrap().to_string();
    let evidence = evidence(&spans);

    let manifest = manifest(&evidence, &agent);

    assert!(
        manifest
            .diagnostics
            .iter()
            .any(|diagnostic| diagnostic.issue.code == "runtime_store_identity_conflict")
    );
    let owners: BTreeSet<&str> = manifest
        .stores
        .iter()
        .map(|store| store.owner_span_id.as_str())
        .collect();
    assert_eq!(
        owners,
        BTreeSet::from([
            agent["span_id"].as_str().unwrap(),
            workflow_span_id.as_str()
        ])
    );
    let workflow_view = manifest
        .stores
        .iter()
        .find(|store| store.owner_span_id == workflow_span_id)
        .expect("the Workflow's Store view");
    assert_eq!(workflow_view.transition_count, 0);
    let workflow_start = evidence.executables_by_span_id[&workflow_span_id].stores()
        [&StoreRole::Application]
        .start
        .as_ref()
        .expect("the Workflow's start state");
    assert_eq!(workflow_start.value, json!({"value": "result-1"}));
}

#[test]
fn a_span_from_another_trace_is_diagnosed_at_trace_scope() {
    let mut spans = nested_workflow_fixture();
    let last = spans.len() - 1;
    spans[last]["trace_id"] = json!("f".repeat(32));
    let evidence = evidence(&spans);
    assert!(evidence.diagnostics.iter().any(|diagnostic| {
        diagnostic.owner_span_id.is_none() && diagnostic.issue.code == "trace_identity_mismatch"
    }));
}
