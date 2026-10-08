//! Generic Store replay and malformed-evidence safety.

mod common;

use junjo_evidence::json::{Json, JsonObject, values_equal};
use junjo_evidence::store_diagnostics::reconstruction::{
    AGENT_STORE_BOUNDARY, StoreOwnerBoundary, StoreReconstructionResult, WORKFLOW_STORE_BOUNDARY,
    reconstruct_store,
};
use junjo_evidence::store_diagnostics::schemas::ReconstructionStatus;
use serde_json::json;

fn payload(attributes: &mut JsonObject, root: &str, value: &Json) {
    attributes.insert(
        root.to_string(),
        json!(serde_json::to_string(value).unwrap()),
    );
    attributes.insert(format!("{root}.mode"), json!("full"));
    attributes.insert(format!("{root}.policy"), json!("junjo.full.v1"));
}

/// The facts of one transition event. Tests override single members.
struct Transition {
    sequence: Json,
    revision_before: Json,
    revision_after: Json,
    event_id: Json,
    action: Json,
    store_name: Json,
}

impl Default for Transition {
    fn default() -> Self {
        Self {
            sequence: json!(1),
            revision_before: json!(0),
            revision_after: json!(1),
            event_id: json!("event-1"),
            action: json!("test"),
            store_name: json!("AgentStore"),
        }
    }
}

/// One Agent owner and one span carrying one transition.
fn store_evidence(
    start: &Json,
    end: &Json,
    patch: &Json,
    transition: Transition,
) -> (JsonObject, Vec<JsonObject>) {
    let mut owner = json!({
        "junjo.agent.state.available": true,
        "junjo.agent.store.id": "store-1",
        "junjo.store.revision.start": 0,
        "junjo.store.revision.end": transition.revision_after,
        "junjo.store.transition.start": 0,
        "junjo.store.transition.end": 1,
        "junjo.store.transition.count": 1,
        "junjo.store.reconstructable": true,
    })
    .as_object()
    .unwrap()
    .clone();
    payload(&mut owner, "junjo.agent.state.start", start);
    payload(&mut owner, "junjo.agent.state.end", end);
    let mut event_attributes = json!({
        "id": transition.event_id,
        "junjo.store.name": transition.store_name,
        "junjo.store.id": "store-1",
        "junjo.store.action": transition.action,
        "junjo.store.transition.sequence": transition.sequence,
        "junjo.store.revision.before": transition.revision_before,
        "junjo.store.revision.after": transition.revision_after,
    })
    .as_object()
    .unwrap()
    .clone();
    payload(&mut event_attributes, "junjo.state_json_patch", patch);
    let span = json!({
        "span_id": "1111111111111111",
        "events_json": [{"name": "set_state", "attributes": event_attributes}],
    });
    (owner, vec![span.as_object().unwrap().clone()])
}

fn reconstruct(
    owner: &JsonObject,
    spans: &[JsonObject],
    boundary: &StoreOwnerBoundary,
) -> StoreReconstructionResult {
    let spans: Vec<&JsonObject> = spans.iter().collect();
    reconstruct_store(owner, &spans, boundary)
}

fn codes(result: &StoreReconstructionResult) -> Vec<&str> {
    result
        .diagnostics
        .iter()
        .map(|item| item.code.as_str())
        .collect()
}

fn event_attributes(spans: &mut [JsonObject]) -> &mut JsonObject {
    spans[0]["events_json"][0]["attributes"]
        .as_object_mut()
        .unwrap()
}

/// Rename the Agent boundary's owner facts to the Workflow boundary's.
fn as_workflow_owner(owner: &JsonObject) -> JsonObject {
    owner
        .iter()
        .filter(|(key, _)| *key != "junjo.agent.state.available")
        .map(|(key, value)| {
            let key = key
                .replace("junjo.agent.store.id", "junjo.workflow.store.id")
                .replace("junjo.agent.state.start", "junjo.workflow.state.start")
                .replace("junjo.agent.state.end", "junjo.workflow.state.end");
            (key, value.clone())
        })
        .collect()
}

fn vectors() -> Json {
    common::read_json(&common::fixture_root().join("store/rfc6902-replay.json"))
}

#[test]
fn reconstructs_full_rfc6902_vectors() {
    for vector in vectors()["valid"].as_array().unwrap() {
        let name = &vector["name"];
        let (owner, spans) = store_evidence(
            &vector["start"],
            &vector["end"],
            &vector["patch"],
            Transition::default(),
        );
        let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
        assert!(result.detail.reconstructable, "{name}");
        assert_eq!(
            result.detail.reconstruction_status,
            ReconstructionStatus::Verified,
            "{name}"
        );
        assert!(result.replay_verified, "{name}");
        assert!(
            values_equal(&result.detail.transitions[0].after, &vector["end"]),
            "{name}"
        );
        assert!(
            result.diagnostics.is_empty(),
            "{name}: {:?}",
            result.diagnostics
        );
    }
}

#[test]
fn invalid_rfc6902_vectors_are_not_reconstructable() {
    for vector in vectors()["invalid"].as_array().unwrap() {
        let name = &vector["name"];
        let (owner, spans) = store_evidence(
            &vector["start"],
            &vector["start"],
            &vector["patch"],
            Transition::default(),
        );
        let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
        assert!(!result.detail.reconstructable, "{name}");
        assert_eq!(
            result.detail.reconstruction_status,
            ReconstructionStatus::Failed,
            "{name}"
        );
        assert!(codes(&result).contains(&"patch_replay_mismatch"), "{name}");
    }
}

#[test]
fn bool_owner_integer_is_rejected() {
    let (mut owner, spans) =
        store_evidence(&json!({}), &json!({}), &json!([]), Transition::default());
    owner.insert("junjo.store.revision.start".to_string(), json!(true));
    let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
    assert!(!result.detail.reconstructable);
    assert!(codes(&result).contains(&"invalid_store_owner_fact"));
}

#[test]
fn mixed_transition_sequences_have_a_total_order_and_partial_diagnostics() {
    let (mut owner, mut spans) = store_evidence(
        &json!({}),
        &json!({}),
        &json!([]),
        Transition {
            sequence: json!("one"),
            revision_after: json!(0),
            ..Transition::default()
        },
    );
    let (_, second_spans) = store_evidence(
        &json!({}),
        &json!({}),
        &json!([]),
        Transition {
            sequence: json!(2),
            revision_after: json!(0),
            ..Transition::default()
        },
    );
    owner.insert("junjo.store.transition.count".to_string(), json!(2));
    owner.insert("junjo.store.transition.end".to_string(), json!(2));
    owner.insert("junjo.store.revision.end".to_string(), json!(0));
    spans.extend(second_spans);
    let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
    assert!(!result.detail.reconstructable);
    assert!(codes(&result).contains(&"transition_sequence_out_of_range"));
}

#[test]
fn missing_event_identity_is_diagnosed_not_coerced() {
    let cases = [
        (
            Transition {
                event_id: Json::Null,
                revision_after: json!(0),
                ..Transition::default()
            },
            "missing_transition_event_id",
        ),
        (
            Transition {
                action: Json::Null,
                revision_after: json!(0),
                ..Transition::default()
            },
            "missing_transition_action",
        ),
    ];
    for (transition, expected) in cases {
        let (owner, spans) = store_evidence(&json!({}), &json!({}), &json!([]), transition);
        let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
        assert!(result.detail.transitions.is_empty());
        assert!(codes(&result).contains(&expected), "{expected}");
    }
}

#[test]
fn invalid_store_name_is_diagnosed_not_coerced() {
    // A lone-surrogate name cannot be constructed here: span text is always
    // Unicode scalar values by the time it is a Rust string.
    for store_name in [Json::Null, json!({}), json!([]), json!("")] {
        let (owner, spans) = store_evidence(
            &json!({}),
            &json!({}),
            &json!([]),
            Transition {
                revision_after: json!(0),
                store_name: store_name.clone(),
                ..Transition::default()
            },
        );
        let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
        assert!(!result.detail.reconstructable, "{store_name}");
        assert!(!result.replay_verified, "{store_name}");
        assert!(
            codes(&result).contains(&"invalid_store_name"),
            "{store_name}"
        );
    }
}

/// Two transitions on one Store that add `a` and then `b`.
fn two_transition_evidence(first: Transition, second: Transition) -> (JsonObject, Vec<JsonObject>) {
    let final_state = json!({"a": 1, "b": 2});
    let (mut owner, mut spans) = store_evidence(
        &json!({}),
        &final_state,
        &json!([{"op": "add", "path": "/a", "value": 1}]),
        first,
    );
    owner.insert("junjo.store.revision.end".to_string(), json!(2));
    owner.insert("junjo.store.transition.count".to_string(), json!(2));
    owner.insert("junjo.store.transition.end".to_string(), json!(2));
    let (_, second_spans) = store_evidence(
        &json!({"a": 1}),
        &final_state,
        &json!([{"op": "add", "path": "/b", "value": 2}]),
        Transition {
            sequence: json!(2),
            revision_before: json!(1),
            revision_after: json!(2),
            event_id: json!("event-2"),
            ..second
        },
    );
    spans.extend(second_spans);
    (owner, spans)
}

#[test]
fn one_store_id_cannot_change_names_between_transitions() {
    let (owner, spans) = two_transition_evidence(
        Transition::default(),
        Transition {
            store_name: json!("RenamedStore"),
            ..Transition::default()
        },
    );
    let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
    assert!(!result.detail.reconstructable);
    assert!(!result.replay_verified);
    assert!(codes(&result).contains(&"invalid_store_name"));
}

#[test]
fn one_store_name_across_distinct_actions_replays_successfully() {
    let (owner, spans) = two_transition_evidence(
        Transition {
            action: json!("first_action"),
            store_name: json!("StableStore"),
            ..Transition::default()
        },
        Transition {
            action: json!("second_action"),
            store_name: json!("StableStore"),
            ..Transition::default()
        },
    );
    let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
    assert!(result.detail.reconstructable);
    assert!(result.replay_verified);
    let actions: Vec<&str> = result
        .detail
        .transitions
        .iter()
        .map(|transition| transition.action.as_str())
        .collect();
    assert_eq!(actions, ["first_action", "second_action"]);
    assert!(result.diagnostics.is_empty(), "{:?}", result.diagnostics);
    assert_eq!(result.detail.transitions[1].before, json!({"a": 1}));
    assert_eq!(result.detail.transitions[1].after, json!({"a": 1, "b": 2}));
}

/// Re-emit the owner state and the patch under a non-inline payload policy.
fn use_payload_mode(owner: &mut JsonObject, spans: &mut [JsonObject], mode: &str) {
    let policy = format!("junjo.{mode}.v1");
    for root in ["junjo.agent.state.start", "junjo.agent.state.end"] {
        owner.remove(root);
        owner.insert(format!("{root}.mode"), json!(mode));
        owner.insert(format!("{root}.policy"), json!(policy));
        if mode == "reference" {
            owner.insert(
                format!("{root}.reference"),
                json!(format!("urn:test:{root}")),
            );
        }
    }
    let attributes = event_attributes(spans);
    attributes.remove("junjo.state_json_patch");
    attributes.insert("junjo.state_json_patch.mode".to_string(), json!(mode));
    attributes.insert("junjo.state_json_patch.policy".to_string(), json!(policy));
    if mode == "reference" {
        attributes.insert(
            "junjo.state_json_patch.reference".to_string(),
            json!("urn:test:patch"),
        );
    }
}

fn unchanged_revision() -> Transition {
    Transition {
        revision_after: json!(0),
        ..Transition::default()
    }
}

#[test]
fn intentional_payload_policy_unavailability_is_not_corruption() {
    for mode in ["excluded", "reference"] {
        let (mut owner, mut spans) =
            store_evidence(&json!({}), &json!({}), &json!([]), unchanged_revision());
        owner.insert("junjo.store.reconstructable".to_string(), json!(false));
        use_payload_mode(&mut owner, &mut spans, mode);
        let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
        assert!(!result.detail.reconstructable, "{mode}");
        assert_eq!(
            result.detail.reconstruction_status,
            ReconstructionStatus::PolicyUnavailable,
            "{mode}"
        );
        assert_eq!(
            result.detail.reconstruction_reason.as_deref(),
            Some("payload_policy")
        );
        assert!(!result.replay_verified);
        assert!(
            result.diagnostics.is_empty(),
            "{mode}: {:?}",
            result.diagnostics
        );
    }
}

#[test]
fn conservative_producer_claim_does_not_override_verified_replay() {
    let (mut owner, spans) = store_evidence(
        &json!({}),
        &json!({"value": 1}),
        &json!([{"op": "add", "path": "/value", "value": 1}]),
        Transition::default(),
    );
    owner.insert("junjo.store.reconstructable".to_string(), json!(false));
    let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
    assert!(!result.detail.reconstructable_claimed);
    assert!(result.detail.reconstructable);
    assert_eq!(
        result.detail.reconstruction_status,
        ReconstructionStatus::Verified
    );
    assert_eq!(result.detail.reconstruction_reason, None);
    assert!(result.diagnostics.is_empty());
}

#[test]
fn producer_reconstructable_claim_requires_independent_verification() {
    let (mut owner, mut spans) =
        store_evidence(&json!({}), &json!({}), &json!([]), unchanged_revision());
    use_payload_mode(&mut owner, &mut spans, "excluded");
    let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
    assert_eq!(
        result.detail.reconstruction_status,
        ReconstructionStatus::Failed
    );
    assert_eq!(
        result.detail.reconstruction_reason.as_deref(),
        Some("reconstructable_claim_mismatch")
    );
    assert_eq!(codes(&result), ["reconstructable_claim_mismatch"]);
}

fn object(value: Json) -> JsonObject {
    value.as_object().unwrap().clone()
}

#[test]
fn state_unavailable_rejects_fabricated_store_evidence() {
    let owner = object(json!({
        "junjo.agent.state.available": false,
        "junjo.agent.runtime_id": "agent-run",
        "junjo.agent.store.id": "fabricated-store",
    }));
    let spans = [object(json!({
        "span_id": "1111111111111111",
        "attributes_json": {"junjo.agent.runtime_id": "agent-run"},
        "events_json": [{"name": "set_state", "attributes": {"junjo.store.id": "fabricated-store"}}],
    }))];
    let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
    assert!(!result.detail.available);
    assert_eq!(
        result.detail.reconstruction_status,
        ReconstructionStatus::NotApplicable
    );
    assert_eq!(
        result.detail.reconstruction_reason.as_deref(),
        Some("state_unavailable")
    );
    assert_eq!(codes(&result), ["fabricated_boundary_store"]);
}

#[test]
fn state_unavailable_ignores_unrelated_workflow_store_events() {
    let owner = object(json!({
        "junjo.agent.state.available": false,
        "junjo.agent.runtime_id": "agent-run",
    }));
    let spans = [object(json!({
        "span_id": "1111111111111111",
        "attributes_json": {
            "junjo.span_type": "workflow",
            "junjo.executable_runtime_id": "workflow-run",
        },
        "events_json": [{"name": "set_state", "attributes": {"junjo.store.id": "workflow-store"}}],
    }))];
    let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
    assert_eq!(
        result.detail.reconstruction_status,
        ReconstructionStatus::NotApplicable
    );
    assert_eq!(
        result.detail.reconstruction_reason.as_deref(),
        Some("state_unavailable")
    );
    assert!(result.diagnostics.is_empty());
}

#[test]
fn state_unavailable_rejects_owner_attributable_store_event_without_owner_facts() {
    let owner = object(json!({
        "junjo.agent.state.available": false,
        "junjo.agent.runtime_id": "agent-run",
    }));
    let spans = [object(json!({
        "span_id": "1111111111111111",
        "attributes_json": {"junjo.agent.runtime_id": "agent-run"},
        "events_json": [{"name": "set_state", "attributes": {"junjo.store.id": "fabricated-store"}}],
    }))];
    let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
    assert_eq!(codes(&result), ["fabricated_boundary_store"]);
}

#[test]
fn absent_or_invalid_state_availability_is_not_applicable() {
    for availability in [Json::Null, json!("true"), json!(1)] {
        let owner = object(json!({"junjo.agent.state.available": availability}));
        let result = reconstruct(&owner, &[], &AGENT_STORE_BOUNDARY);
        assert!(!result.detail.available);
        assert_eq!(
            result.detail.reconstruction_reason.as_deref(),
            Some("invalid_state_availability")
        );
        assert_eq!(codes(&result), ["invalid_store_owner_fact"]);
    }
}

#[test]
fn a_missing_store_id_fails_before_any_replay() {
    let (mut owner, spans) =
        store_evidence(&json!({}), &json!({}), &json!([]), unchanged_revision());
    owner.remove("junjo.agent.store.id");
    let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
    assert!(result.detail.available);
    assert_eq!(
        result.detail.reconstruction_status,
        ReconstructionStatus::Failed
    );
    assert_eq!(
        result.detail.reconstruction_reason.as_deref(),
        Some("missing_store_id")
    );
    assert_eq!(result.detail.start, None);
    assert_eq!(codes(&result), ["missing_store_id"]);
}

#[test]
fn store_reconstruction_rejects_noncanonical_transition_carrier_identity() {
    for boundary in [&AGENT_STORE_BOUNDARY, &WORKFLOW_STORE_BOUNDARY] {
        let (mut owner, mut spans) = store_evidence(
            &json!({}),
            &json!({"value": 1}),
            &json!([{"op": "add", "path": "/value", "value": 1}]),
            Transition::default(),
        );
        if boundary.availability_attribute.is_none() {
            owner = as_workflow_owner(&owner);
        }
        spans[0].insert("span_id".to_string(), json!("not-a-span-id"));
        let result = reconstruct(&owner, &spans, boundary);
        assert!(!result.detail.reconstructable);
        assert_eq!(
            result.detail.reconstruction_status,
            ReconstructionStatus::Failed
        );
        assert!(result.detail.transitions.is_empty());
        assert!(codes(&result).contains(&"invalid_span_id"));
    }
}

#[test]
fn agent_and_workflow_boundaries_share_exact_replay_semantics() {
    let (owner, spans) = store_evidence(
        &json!({"value": 0}),
        &json!({"value": 1}),
        &json!([{"op": "replace", "path": "/value", "value": 1}]),
        Transition::default(),
    );
    let agent = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
    let workflow = reconstruct(&as_workflow_owner(&owner), &spans, &WORKFLOW_STORE_BOUNDARY);
    assert_eq!(workflow.detail, agent.detail);
    assert!(agent.diagnostics.is_empty());
    assert!(workflow.diagnostics.is_empty());
}

#[test]
fn replayed_state_must_match_the_emitted_end_state() {
    let (owner, spans) = store_evidence(
        &json!({"value": 0}),
        &json!({"value": 2}),
        &json!([{"op": "replace", "path": "/value", "value": 1}]),
        Transition::default(),
    );
    let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
    assert!(!result.detail.reconstructable);
    assert_eq!(
        codes(&result),
        ["patch_replay_mismatch", "reconstructable_claim_mismatch"]
    );
    assert_eq!(
        result.detail.reconstruction_reason.as_deref(),
        Some("patch_replay_mismatch")
    );
    assert_eq!(result.diagnostics[0].path, "junjo.agent.state.end");
}

#[test]
fn a_number_written_as_a_float_still_matches_its_integer() {
    let (owner, spans) = store_evidence(
        &json!({"value": 0}),
        &json!({"value": 1.0}),
        &json!([{"op": "replace", "path": "/value", "value": 1}]),
        Transition::default(),
    );
    let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
    assert!(result.detail.reconstructable, "{:?}", result.diagnostics);
}

#[test]
fn sequence_gaps_and_missing_trailing_transitions_have_distinct_codes() {
    let (mut owner, spans) =
        store_evidence(&json!({}), &json!({}), &json!([]), unchanged_revision());
    owner.insert("junjo.store.transition.count".to_string(), json!(2));
    owner.insert("junjo.store.transition.end".to_string(), json!(2));
    let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
    assert!(codes(&result).contains(&"transition_sequence_missing_trailing"));

    let (mut owner, spans) = store_evidence(
        &json!({}),
        &json!({}),
        &json!([]),
        Transition {
            sequence: json!(2),
            revision_after: json!(0),
            ..Transition::default()
        },
    );
    owner.insert("junjo.store.transition.count".to_string(), json!(2));
    owner.insert("junjo.store.transition.end".to_string(), json!(2));
    let result = reconstruct(&owner, &spans, &AGENT_STORE_BOUNDARY);
    assert!(codes(&result).contains(&"transition_sequence_gap"));
}
