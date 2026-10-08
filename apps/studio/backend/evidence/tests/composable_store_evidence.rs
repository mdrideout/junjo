//! Shared physical events retain separate, independently verified execution
//! views.

mod common;

use junjo_evidence::json::Json;
use junjo_evidence::store_diagnostics::schemas::StoreBoundaryDetail;
use junjo_evidence::trace_evidence::assembler::{assemble_trace_evidence, hydrate_store_view};
use junjo_evidence::trace_evidence::schemas::{
    ExecutableAnnotation, OwnerExecutableType, StoreRole, TraceEvidence,
};
use serde_json::json;

/// The fixture in which an Agent lends the application Store it borrowed to
/// a nested Workflow.
fn fixture() -> Json {
    common::read_json(&common::fixture_root().join("agent/producer/shared_application_store.json"))
}

fn evidence(fixture: &Json) -> TraceEvidence {
    let trace_id = fixture["trace_id"].as_str().expect("a trace identifier");
    let spans = serde_json::from_value(fixture["spans"].clone()).expect("normalized spans");
    assemble_trace_evidence(trace_id, spans)
}

/// The first fixture span of one Junjo type.
fn span_of_type<'a>(fixture: &'a Json, span_type: &str) -> &'a Json {
    fixture["spans"]
        .as_array()
        .unwrap()
        .iter()
        .find(|span| span["attributes_json"]["junjo.span_type"] == span_type)
        .unwrap_or_else(|| panic!("a {span_type} span"))
}

/// The first annotated executable of one type.
fn executable(
    evidence: &TraceEvidence,
    executable_type: OwnerExecutableType,
) -> &ExecutableAnnotation {
    evidence
        .executables_by_span_id
        .values()
        .find(|executable| executable.executable_type() == executable_type)
        .expect("an executable of that type")
}

fn store(executable: &ExecutableAnnotation, role: StoreRole) -> &StoreBoundaryDetail {
    &executable.stores()[&role]
}

#[test]
fn shared_store_views_are_independent_and_events_are_not_duplicated() {
    let evidence = evidence(&fixture());
    let agent = executable(&evidence, OwnerExecutableType::Agent);
    let workflow = executable(&evidence, OwnerExecutableType::Workflow);

    let app = store(agent, StoreRole::Application);
    let child = store(workflow, StoreRole::Application);
    assert_eq!(app.store_id, child.store_id);
    assert_ne!(app.store_id, store(agent, StoreRole::Runtime).store_id);
    assert_eq!(
        (app.sequence_start, app.sequence_end, app.revision_start),
        (Some(2), Some(5), Some(1))
    );
    assert_eq!(
        (
            child.sequence_start,
            child.sequence_end,
            child.revision_start
        ),
        (Some(3), Some(4), Some(2))
    );
    let shared_store_id = app.store_id.as_ref().expect("a shared Store ID");
    assert_eq!(evidence.stores_by_id[shared_store_id].transitions.len(), 3);
    let child_sequences: Vec<i64> = hydrate_store_view(child, &evidence.stores_by_id)
        .transitions
        .iter()
        .map(|item| item.sequence)
        .collect();
    assert_eq!(child_sequences, [4]);
    assert!(app.reconstructable && child.reconstructable);
    assert!(
        evidence.diagnostics.is_empty(),
        "{:?}",
        evidence.diagnostics
    );
}

#[test]
fn missing_shared_writer_only_invalidates_views_that_need_its_event() {
    let mut fixture = fixture();
    for span in fixture["spans"].as_array_mut().unwrap() {
        span["events_json"]
            .as_array_mut()
            .unwrap()
            .retain(|event| event["attributes"]["id"] != "event-shared-3");
    }

    let evidence = evidence(&fixture);

    let agent = executable(&evidence, OwnerExecutableType::Agent);
    let workflow = executable(&evidence, OwnerExecutableType::Workflow);
    assert!(!store(agent, StoreRole::Application).reconstructable);
    assert!(store(agent, StoreRole::Runtime).reconstructable);
    assert!(store(workflow, StoreRole::Application).reconstructable);
    let hydrated = hydrate_store_view(store(agent, StoreRole::Application), &evidence.stores_by_id);
    assert!(
        hydrated
            .transitions
            .iter()
            .all(|item| item.before.is_null())
    );
    assert!(
        evidence
            .diagnostics
            .iter()
            .any(|item| item.issue.code == "transition_sequence_gap")
    );
}

#[test]
fn overlapping_views_on_same_store_keep_their_own_checkpoints() {
    let mut fixture = fixture();
    let agent = span_of_type(&fixture, "agent").clone();
    let original = span_of_type(&fixture, "workflow").clone();
    // A second Workflow on the same Store that observed the Agent's interval.
    let mut sibling = original.clone();
    sibling["span_id"] = json!("f".repeat(16));
    let attributes = sibling["attributes_json"].as_object_mut().unwrap();
    attributes.insert(
        "junjo.executable_runtime_id".to_string(),
        json!("overlapping-workflow"),
    );
    for suffix in [
        "revision.start",
        "revision.end",
        "transition.start",
        "transition.end",
        "transition.count",
    ] {
        attributes.insert(
            format!("junjo.store.{suffix}"),
            agent["attributes_json"][format!("junjo.agent.application_store.{suffix}")].clone(),
        );
    }
    for suffix in ["start", "end"] {
        attributes.insert(
            format!("junjo.workflow.state.{suffix}"),
            agent["attributes_json"][format!("junjo.agent.application_state.{suffix}")].clone(),
        );
    }
    fixture["spans"].as_array_mut().unwrap().push(sibling);

    let evidence = evidence(&fixture);

    let view = |span_id: &str| {
        store(
            &evidence.executables_by_span_id[span_id],
            StoreRole::Application,
        )
    };
    let narrow = view(original["span_id"].as_str().unwrap());
    let wide = view(&"f".repeat(16));
    assert!(narrow.reconstructable && wide.reconstructable);
    let narrow_start = narrow.start.as_ref().expect("the narrow start state");
    let wide_start = wide.start.as_ref().expect("the wide start state");
    assert_eq!(narrow_start.value, json!({"value": "tool"}));
    assert_eq!(wide_start.value, json!({"value": "prepared"}));
    assert_eq!((narrow.transition_count, wide.transition_count), (1, 3));
    let shared_store_id = wide.store_id.as_ref().expect("a shared Store ID");
    assert_eq!(evidence.stores_by_id[shared_store_id].transitions.len(), 3);
}
