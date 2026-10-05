//! Canonical-fixture conformance for Agent semantic projections.

mod common;

use std::collections::BTreeSet;

use junjo_evidence::agent_diagnostics::assembler::{assemble_agent_detail, assemble_agent_summary};
use junjo_evidence::agent_diagnostics::schemas::{
    Admission, AgentEvidenceError, AgentExecutionDetail, AgentOperation, ExecutableType, Outcome,
    RequestedToolCallReason, ResponseType,
};
use junjo_evidence::json::{Json, JsonObject};
use junjo_evidence::store_diagnostics::schemas::{
    IntegrityStatus, PayloadMode, ReconstructionStatus,
};
use serde_json::json;

const OPERATION_TYPE: &str = "junjo.agent.operation_type";

/// Every valid producer and consumer fixture, in the generator's order.
fn valid_fixtures() -> Vec<Json> {
    let agent = common::fixture_root().join("agent");
    let mut paths = common::json_files(&agent.join("producer"));
    paths.extend(common::json_files(&agent.join("consumer")));
    paths.sort();
    paths.iter().map(|path| common::read_json(path)).collect()
}

/// The spans of one producer fixture, owned so a test can corrupt them.
fn producer(name: &str) -> Vec<JsonObject> {
    let path = common::fixture_root().join(format!("agent/producer/{name}.json"));
    common::spans(&common::read_json(&path))
        .into_iter()
        .cloned()
        .collect()
}

fn attribute<'a>(span: &'a JsonObject, key: &str) -> &'a Json {
    span["attributes_json"].get(key).unwrap_or(&Json::Null)
}

fn attributes(span: &mut JsonObject) -> &mut JsonObject {
    span["attributes_json"].as_object_mut().unwrap()
}

fn agent_owners(spans: &[JsonObject]) -> Vec<usize> {
    (0..spans.len())
        .filter(|index| common::span_type(&spans[*index]) == Some("agent"))
        .collect()
}

fn first_owner(spans: &[JsonObject]) -> usize {
    agent_owners(spans)[0]
}

fn operation(spans: &[JsonObject], operation_type: &str) -> usize {
    spans
        .iter()
        .position(|span| attribute(span, OPERATION_TYPE) == operation_type)
        .unwrap_or_else(|| panic!("a {operation_type} operation"))
}

fn first_store_event(spans: &mut [JsonObject]) -> &mut JsonObject {
    spans
        .iter_mut()
        .flat_map(|span| span["events_json"].as_array_mut().unwrap())
        .find(|event| event["name"] == "set_state")
        .expect("a Store event")["attributes"]
        .as_object_mut()
        .unwrap()
}

fn assemble(
    spans: &[JsonObject],
    owner: usize,
) -> Result<AgentExecutionDetail, AgentEvidenceError> {
    let references: Vec<&JsonObject> = spans.iter().collect();
    assemble_agent_detail(references[owner], &references, None)
}

fn detail(spans: &[JsonObject], owner: usize) -> AgentExecutionDetail {
    assemble(spans, owner).unwrap_or_else(|error| panic!("a detail, not {error:?}"))
}

fn codes(detail: &AgentExecutionDetail) -> BTreeSet<&str> {
    detail
        .integrity
        .diagnostics
        .iter()
        .map(|issue| issue.code.as_str())
        .collect()
}

/// The codes from the typed error when no detail can be assembled, and from
/// integrity otherwise.
fn observed_codes(result: Result<AgentExecutionDetail, AgentEvidenceError>) -> BTreeSet<String> {
    let diagnostics = match result {
        Ok(detail) => detail.integrity.diagnostics,
        Err(error) => error.diagnostics,
    };
    diagnostics.into_iter().map(|issue| issue.code).collect()
}

fn set_payload(attributes: &mut JsonObject, root: &str, raw: &str, mode: &str, policy: &str) {
    attributes.insert(root.to_string(), json!(raw));
    attributes.insert(format!("{root}.mode"), json!(mode));
    attributes.insert(format!("{root}.policy"), json!(policy));
}

#[test]
fn summaries_need_only_the_owner_span() {
    for fixture in valid_fixtures() {
        let spans: Vec<JsonObject> = common::spans(&fixture).into_iter().cloned().collect();
        for owner in agent_owners(&spans) {
            let summary = assemble_agent_summary(&spans[owner]).unwrap();
            assert_eq!(summary, detail(&spans, owner).summary);
        }
    }
}

#[test]
fn invalid_agent_derivatives_report_their_declared_diagnostic() {
    let paths = common::json_files(&common::fixture_root().join("invalid/agent"));
    assert!(!paths.is_empty());
    for path in paths {
        let case = common::read_json(&path);
        let expected = case["expected_diagnostic"].as_str().unwrap();
        let spans: Vec<JsonObject> = common::spans(&case["fixture"])
            .into_iter()
            .cloned()
            .collect();
        let observed = observed_codes(assemble(&spans, first_owner(&spans)));
        assert!(
            observed.contains(expected),
            "{}: expected {expected}, observed {observed:?}",
            common::file_stem(&path)
        );
    }
}

#[test]
fn owner_from_separate_query_is_matched_by_transport_identity() {
    let spans = producer("direct_typed_completion");
    let separate_owner = spans[first_owner(&spans)].clone();
    let references: Vec<&JsonObject> = spans.iter().collect();

    let detail = assemble_agent_detail(&separate_owner, &references, None).unwrap();

    assert_eq!(detail.integrity.status, IntegrityStatus::Complete);
    assert!(!codes(&detail).contains("store_causal_owner_mismatch"));
}

#[test]
fn state_unavailable_agent_ignores_unrelated_workflow_store_event() {
    let mut spans = producer("boundary_input_history_rejection");
    let mut unrelated = spans[0].clone();
    unrelated.insert("span_id".to_string(), json!("ffffffffffffffff"));
    unrelated.insert("name".to_string(), json!("Unrelated Workflow"));
    unrelated.insert(
        "attributes_json".to_string(),
        json!({
            "junjo.telemetry.contract_version": 3,
            "junjo.span_type": "workflow",
            "junjo.executable_runtime_id": "workflow-run",
        }),
    );
    unrelated.insert(
        "events_json".to_string(),
        json!([{"name": "set_state", "attributes": {"junjo.store.id": "workflow-store"}}]),
    );
    spans.push(unrelated);

    let detail = detail(&spans, 0);

    assert_eq!(
        detail.state.reconstruction_status,
        ReconstructionStatus::NotApplicable
    );
    assert_eq!(detail.integrity.status, IntegrityStatus::Complete);
}

#[test]
fn state_unavailable_agent_rejects_store_event_on_its_owner_span() {
    let mut spans = producer("boundary_input_history_rejection");
    spans[0]["events_json"].as_array_mut().unwrap().push(json!({
        "name": "set_state",
        "attributes": {"junjo.store.id": "fabricated-store"},
    }));

    let detail = detail(&spans, 0);

    assert_eq!(detail.integrity.status, IntegrityStatus::Partial);
    assert!(codes(&detail).contains("fabricated_boundary_store"));
}

#[test]
fn agent_store_excludes_transition_on_noncanonical_operation_span() {
    let mut spans = producer("direct_typed_completion");
    let owner = first_owner(&spans);
    let model = operation(&spans, "model_request");
    spans[model].insert("span_id".to_string(), json!("not-a-span-id"));

    let detail = detail(&spans, owner);

    assert_eq!(detail.integrity.status, IntegrityStatus::Partial);
    assert_eq!(
        detail.state.reconstruction_status,
        ReconstructionStatus::Failed
    );
    assert!(
        detail
            .state
            .transitions
            .iter()
            .all(|transition| transition.span_id != "not-a-span-id")
    );
    assert!(codes(&detail).contains("invalid_span_id"));
}

/// Whether an attribute is one the semantic backend reads.
fn is_consumed_attribute(key: &str) -> bool {
    [
        "junjo.agent.",
        "junjo.executable_",
        "junjo.parent_executable_",
        "junjo.store.",
    ]
    .iter()
    .any(|prefix| key.starts_with(prefix))
        || [
            "junjo.telemetry.contract_version",
            "junjo.span_type",
            "junjo.cancelled",
            "junjo.cancelled_reason",
            "error.type",
        ]
        .contains(&key)
}

/// Replacing any consumed attribute with an object or an array must end as a
/// typed error or as partial evidence, in four canonical contexts.
#[test]
fn bounded_semantic_scalar_mutations_never_escape_typed_evidence_handling() {
    let mut exercised = 0;
    for fixture_name in [
        "direct_typed_completion",
        "malformed_tool_arguments",
        "boundary_input_history_rejection",
        "tool_invokes_nested_workflow",
    ] {
        let spans = producer(fixture_name);
        let owner = first_owner(&spans);
        let runtime_id = attribute(&spans[owner], "junjo.agent.runtime_id").clone();
        let operation_span_ids: Vec<&Json> = spans
            .iter()
            .filter(|span| {
                attribute(span, "junjo.agent.runtime_id") == &runtime_id
                    && span["attributes_json"].get(OPERATION_TYPE).is_some()
            })
            .map(|span| &span["span_id"])
            .collect();
        let mut seen_roles = BTreeSet::new();
        for (index, span) in spans.iter().enumerate() {
            let is_evidence = index == owner
                || attribute(span, "junjo.agent.runtime_id") == &runtime_id
                || span
                    .get("parent_span_id")
                    .is_some_and(|parent| operation_span_ids.contains(&parent));
            if !is_evidence {
                continue;
            }
            for key in span["attributes_json"].as_object().unwrap().keys() {
                if !is_consumed_attribute(key) || !seen_roles.insert(key.clone()) {
                    continue;
                }
                for malformed in [json!({}), json!([])] {
                    let mut corrupted = spans.clone();
                    attributes(&mut corrupted[index]).insert(key.clone(), malformed.clone());
                    match assemble(&corrupted, owner) {
                        Err(error) => assert!(
                            !error.diagnostics.is_empty(),
                            "{fixture_name} {key} {malformed}"
                        ),
                        Ok(detail) => {
                            assert_eq!(
                                detail.integrity.status,
                                IntegrityStatus::Partial,
                                "{fixture_name} {key} {malformed}"
                            );
                            assert!(!detail.integrity.diagnostics.is_empty());
                        }
                    }
                    exercised += 1;
                }
            }
        }
    }
    assert!(exercised > 100, "only {exercised} mutations ran");
}

#[test]
fn redacted_operation_payloads_do_not_create_false_integrity_failures() {
    let mut spans = producer("direct_typed_completion");
    let owner = first_owner(&spans);
    let model = operation(&spans, "model_request");
    for (root, raw) in [
        ("junjo.agent.model.request", r#"{"request": "redacted"}"#),
        (
            "junjo.agent.model.response_candidate",
            r#"{"candidate": "redacted"}"#,
        ),
        ("junjo.agent.model.response", r#"{"response": "redacted"}"#),
    ] {
        set_payload(
            attributes(&mut spans[model]),
            root,
            raw,
            "redacted",
            "fixture.redacted.v1",
        );
    }

    let detail = detail(&spans, owner);

    assert_eq!(
        detail.integrity.status,
        IntegrityStatus::Complete,
        "{:?}",
        codes(&detail)
    );
    let AgentOperation::Model(model) = &detail.operations[0] else {
        panic!("a Model operation");
    };
    assert_eq!(model.response_type, Some(ResponseType::FinalOutput));
    assert!(model.usage.is_some());
}

#[test]
fn schema_shaped_redacted_definition_is_not_treated_as_original_content() {
    let mut spans = producer("direct_typed_completion");
    let owner = first_owner(&spans);
    let raw = attribute(&spans[owner], "junjo.agent.definition_snapshot")
        .as_str()
        .unwrap();
    let mut definition: Json = serde_json::from_str(raw).unwrap();
    definition["agentKey"] = json!("redacted-agent-key");
    definition["structuralId"] = json!(format!("agent_sha256:{}", "0".repeat(64)));
    set_payload(
        attributes(&mut spans[owner]),
        "junjo.agent.definition_snapshot",
        &definition.to_string(),
        "redacted",
        "fixture.redacted.v1",
    );

    let detail = detail(&spans, owner);

    assert_eq!(
        detail.integrity.status,
        IntegrityStatus::Complete,
        "{:?}",
        codes(&detail)
    );
    assert_eq!(detail.definition.mode, PayloadMode::Redacted);
}

#[test]
fn noncanonical_full_definition_is_partial_not_an_assembler_failure() {
    let original = producer("direct_typed_completion");
    let owner = first_owner(&original);
    let raw = attribute(&original[owner], "junjo.agent.definition_snapshot")
        .as_str()
        .unwrap();
    let mut unsafe_integer: Json = serde_json::from_str(raw).unwrap();
    unsafe_integer["model"]["settings"]["unsafeInteger"] = json!(9_007_199_254_740_992_i64);
    let mut lone_surrogate: Json = serde_json::from_str(raw).unwrap();
    lone_surrogate["instructions"] = json!("SURROGATE");
    // The escape is written into the payload text. No Rust string can hold
    // the code point itself.
    let lone_surrogate = lone_surrogate.to_string().replace("SURROGATE", "\\ud800");

    for corrupted in [unsafe_integer.to_string(), lone_surrogate] {
        let mut spans = original.clone();
        attributes(&mut spans[owner]).insert(
            "junjo.agent.definition_snapshot".to_string(),
            json!(corrupted),
        );

        let detail = detail(&spans, owner);

        assert_eq!(detail.integrity.status, IntegrityStatus::Partial);
        assert!(
            codes(&detail).contains("nonportable_json_value"),
            "{corrupted}"
        );
    }
}

#[test]
fn malformed_operation_event_evidence_is_partial_not_an_assembler_failure() {
    for (events, expected_code) in [
        (Json::Null, "missing_operation_event_evidence"),
        (json!({"not": "a list"}), "invalid_operation_event_evidence"),
        (json!(["not an event"]), "invalid_operation_event_evidence"),
    ] {
        let mut spans = producer("direct_typed_completion");
        let owner = first_owner(&spans);
        let model = operation(&spans, "model_request");
        spans[model].insert("events_json".to_string(), events);

        let detail = detail(&spans, owner);

        assert_eq!(detail.integrity.status, IntegrityStatus::Partial);
        assert!(codes(&detail).contains(expected_code), "{expected_code}");
    }
}

#[test]
fn observed_tool_operation_survives_unknown_admission_when_store_replay_is_partial() {
    let mut spans = producer("ordered_multiple_tools");
    let owner = first_owner(&spans);
    first_store_event(&mut spans).shift_remove("junjo.store.action");

    let detail = detail(&spans, owner);

    let requested: Vec<_> = detail
        .operations
        .iter()
        .filter_map(AgentOperation::as_model)
        .flat_map(|operation| &operation.requested_tool_calls)
        .collect();
    assert_eq!(detail.integrity.status, IntegrityStatus::Partial);
    assert!(!requested.is_empty());
    assert!(requested.iter().any(|call| {
        call.observed_tool_operation
            && call.admission == Admission::Unknown
            && call.reason == Some(RequestedToolCallReason::StoreEvidenceUnavailable)
    }));
}

#[test]
fn agent_store_event_on_unowned_span_is_diagnostic_not_replayed() {
    let mut spans = producer("direct_typed_completion");
    let owner = first_owner(&spans);
    let model = operation(&spans, "model_request");
    let mut unrelated = spans[model].clone();
    let first_event = unrelated["events_json"][0].clone();
    unrelated.insert("span_id".to_string(), json!("ffffffffffffffff"));
    unrelated.insert("parent_span_id".to_string(), Json::Null);
    unrelated.insert(
        "attributes_json".to_string(),
        json!({"junjo.telemetry.contract_version": 3}),
    );
    unrelated.insert("events_json".to_string(), json!([first_event]));
    spans.push(unrelated);

    let detail = detail(&spans, owner);

    assert_eq!(detail.integrity.status, IntegrityStatus::Partial);
    assert!(detail.state.reconstructable);
    assert!(codes(&detail).contains("store_causal_owner_mismatch"));
}

#[test]
fn ineligible_operation_evidence_cannot_verify_agent_store_replay() {
    for (mutation, expected_code) in [
        ("unsupported_contract", "unsupported_contract"),
        ("missing_contract", "unsupported_contract"),
        ("owner_key", "operation_owner_mismatch"),
        ("physical_parent", "operation_owner_mismatch"),
    ] {
        let mut spans = producer("direct_typed_completion");
        let owner = first_owner(&spans);
        let model = operation(&spans, "model_request");
        match mutation {
            "unsupported_contract" => {
                attributes(&mut spans[model])
                    .insert("junjo.telemetry.contract_version".to_string(), json!(1));
            }
            "missing_contract" => {
                attributes(&mut spans[model]).shift_remove("junjo.telemetry.contract_version");
            }
            "owner_key" => {
                attributes(&mut spans[model])
                    .insert("junjo.agent.key".to_string(), json!("different-agent"));
            }
            _ => {
                spans[model].insert("parent_span_id".to_string(), json!("ffffffffffffffff"));
            }
        }

        let detail = detail(&spans, owner);

        assert_eq!(
            detail.integrity.status,
            IntegrityStatus::Partial,
            "{mutation}"
        );
        assert_eq!(
            detail.state.reconstruction_status,
            ReconstructionStatus::Failed,
            "{mutation}"
        );
        assert!(!detail.state.reconstructable, "{mutation}");
        assert!(codes(&detail).contains(expected_code), "{mutation}");
    }
}

#[test]
fn nonscalar_semantic_evidence_never_escapes_typed_evidence_handling() {
    let cases = [
        (
            "owner_type",
            "direct_typed_completion",
            "invalid_agent_owner_type",
        ),
        (
            "owner_outcome",
            "direct_typed_completion",
            "invalid_terminal_fact",
        ),
        (
            "operation_type",
            "direct_typed_completion",
            "invalid_operation_type",
        ),
        (
            "payload_mode",
            "direct_typed_completion",
            "invalid_payload_slot",
        ),
        (
            "response_type",
            "direct_typed_completion",
            "invalid_model_response",
        ),
        (
            "limit_kind",
            "model_request_limit_exhaustion",
            "invalid_limit_evidence",
        ),
        (
            "parent_type",
            "nested_agent_owner_isolation",
            "parent_executable_correspondence_mismatch",
        ),
        (
            "nested_executable_type",
            "tool_invokes_nested_workflow",
            "invalid_nested_executable",
        ),
    ];
    for (case, fixture_name, expected_code) in cases {
        for malformed in [json!({}), json!([])] {
            let mut spans = producer(fixture_name);
            let owners = agent_owners(&spans);
            let owner = if case == "parent_type" {
                *owners
                    .iter()
                    .find(|owner| {
                        spans[**owner]["attributes_json"]
                            .get("junjo.parent_executable_type")
                            .is_some()
                    })
                    .expect("an owner with a declared parent")
            } else {
                owners[0]
            };
            let (target, key) = match case {
                "owner_type" => (owner, "junjo.span_type"),
                "owner_outcome" => (owner, "junjo.agent.outcome"),
                "operation_type" => (
                    spans
                        .iter()
                        .position(|span| span["attributes_json"].get(OPERATION_TYPE).is_some())
                        .unwrap(),
                    OPERATION_TYPE,
                ),
                "payload_mode" => (owner, "junjo.agent.definition_snapshot.mode"),
                "response_type" => (
                    operation(&spans, "model_request"),
                    "junjo.agent.model.response_type",
                ),
                "limit_kind" => (owner, "junjo.agent.limit.exceeded"),
                "parent_type" => (owner, "junjo.parent_executable_type"),
                _ => (
                    spans
                        .iter()
                        .position(|span| common::span_type(span) == Some("workflow"))
                        .unwrap(),
                    "junjo.span_type",
                ),
            };
            attributes(&mut spans[target]).insert(key.to_string(), malformed.clone());

            let result = assemble(&spans, owner);

            if let Ok(detail) = &result {
                assert_eq!(detail.integrity.status, IntegrityStatus::Partial, "{case}");
            }
            let observed = observed_codes(result);
            assert!(
                observed.contains(expected_code),
                "{case} {malformed}: {observed:?}"
            );
        }
    }
}

#[test]
fn non_completed_agent_omits_unexpected_output_as_partial_evidence() {
    let mut spans = producer("over_budget_tool_batch");
    let owner = first_owner(&spans);
    set_payload(
        attributes(&mut spans[owner]),
        "junjo.agent.output",
        "null",
        "full",
        "junjo.full.v1",
    );

    let detail = detail(&spans, owner);

    assert_eq!(detail.summary.outcome, Outcome::Failed);
    assert_eq!(detail.output, None);
    assert_eq!(detail.integrity.status, IntegrityStatus::Partial);
    assert!(codes(&detail).contains("unexpected_output_evidence"));
}

#[test]
fn nonscalar_store_action_is_partial_not_an_assembler_failure() {
    for malformed in [json!({}), json!([])] {
        let mut spans = producer("direct_typed_completion");
        let owner = first_owner(&spans);
        first_store_event(&mut spans).insert("junjo.store.action".to_string(), malformed);

        let detail = detail(&spans, owner);

        assert_eq!(detail.integrity.status, IntegrityStatus::Partial);
        assert!(codes(&detail).contains("store_causal_owner_mismatch"));
    }
}

#[test]
fn duplicate_payload_object_name_is_rejected_before_last_key_wins() {
    let mut spans = producer("direct_typed_completion");
    let owner = first_owner(&spans);
    let raw = attribute(&spans[owner], "junjo.agent.definition_snapshot")
        .as_str()
        .unwrap();
    let shadowed = format!("{{\"agentKey\":\"shadowed\",{}", &raw[1..]);
    attributes(&mut spans[owner]).insert(
        "junjo.agent.definition_snapshot".to_string(),
        json!(shadowed),
    );

    let detail = detail(&spans, owner);

    assert_eq!(detail.integrity.status, IntegrityStatus::Partial);
    assert!(codes(&detail).contains("duplicate_json_object_name"));
}

#[test]
fn malformed_ambient_parent_span_id_is_partial() {
    for parent_span_id in ["bad", "ABCDEF0123456789"] {
        let mut spans = producer("direct_typed_completion");
        let owner = first_owner(&spans);
        spans[owner].insert("parent_span_id".to_string(), json!(parent_span_id));

        let detail = detail(&spans, owner);

        assert_eq!(detail.integrity.status, IntegrityStatus::Partial);
        assert_eq!(detail.parent_executable, None);
        assert!(codes(&detail).contains("invalid_parent_executable"));
    }
}

#[test]
fn operation_from_wrong_trace_is_not_admitted_to_owner_projection() {
    let mut spans = producer("direct_typed_completion");
    let owner = first_owner(&spans);
    let model = operation(&spans, "model_request");
    spans[model].insert("trace_id".to_string(), json!("not-the-owner-trace"));

    let detail = detail(&spans, owner);

    assert_eq!(detail.integrity.status, IntegrityStatus::Partial);
    assert!(detail.operations.is_empty());
    assert!(codes(&detail).contains("operation_owner_mismatch"));
}

#[test]
fn inverted_operation_interval_is_omitted_with_typed_partial_evidence() {
    let mut spans = producer("direct_typed_completion");
    let owner = first_owner(&spans);
    let model = operation(&spans, "model_request");
    spans[model].insert("end_time".to_string(), json!("2026-01-01T00:00:00+00:00"));

    let detail = detail(&spans, owner);

    assert_eq!(detail.integrity.status, IntegrityStatus::Partial);
    assert!(detail.operations.is_empty());
    assert!(codes(&detail).contains("invalid_span_interval"));
}

/// The Workflow span nested under the Tool operation of the nested fixture.
fn nested_workflow(spans: &[JsonObject]) -> usize {
    let tool = &spans[operation(spans, "tool")]["span_id"];
    spans
        .iter()
        .position(|span| {
            span.get("parent_span_id") == Some(tool) && common::span_type(span) == Some("workflow")
        })
        .expect("a nested Workflow")
}

#[test]
fn malformed_nested_executable_identity_is_not_coerced() {
    let cases: [(&str, &str, Option<Json>); 6] = [
        (
            "attributes",
            "junjo.executable_definition_id",
            Some(Json::Null),
        ),
        (
            "attributes",
            "junjo.executable_runtime_id",
            Some(json!(123)),
        ),
        (
            "attributes",
            "junjo.executable_structural_id",
            Some(json!("")),
        ),
        ("span", "name", None),
        ("span", "span_id", Some(Json::Null)),
        ("span", "trace_id", Some(json!(123))),
    ];
    for (scope, key, value) in cases {
        let mut spans = producer("tool_invokes_nested_workflow");
        let owner = first_owner(&spans);
        let nested = nested_workflow(&spans);
        let target = if scope == "attributes" {
            attributes(&mut spans[nested])
        } else {
            &mut spans[nested]
        };
        match value {
            Some(value) => {
                target.insert(key.to_string(), value);
            }
            None => {
                target.shift_remove(key);
            }
        }

        let detail = detail(&spans, owner);

        assert_eq!(detail.integrity.status, IntegrityStatus::Partial, "{key}");
        assert!(detail.nested_executables.is_empty(), "{key}");
        let observed = codes(&detail);
        assert!(
            observed.contains("invalid_nested_executable")
                || observed.contains("invalid_nested_executable_parent"),
            "{key}: {observed:?}"
        );
    }
}

#[test]
fn unsupported_nested_executable_is_not_exposed_as_complete_evidence() {
    let mut spans = producer("tool_invokes_nested_workflow");
    let owner = first_owner(&spans);
    let nested = nested_workflow(&spans);
    attributes(&mut spans[nested]).insert("junjo.telemetry.contract_version".to_string(), json!(1));

    let detail = detail(&spans, owner);

    assert_eq!(detail.integrity.status, IntegrityStatus::Partial);
    assert!(detail.nested_executables.is_empty());
    assert!(codes(&detail).contains("unsupported_contract"));
}

/// The outer and nested Agent owners of the nested-owner fixture.
fn outer_and_nested_owners(spans: &[JsonObject]) -> (usize, usize) {
    let owners = agent_owners(spans);
    let is_root = |owner: &&usize| spans[**owner]["parent_span_id"].is_null();
    let outer = *owners.iter().find(is_root).expect("a root Agent");
    let nested = *owners
        .iter()
        .find(|owner| !is_root(owner))
        .expect("a nested Agent");
    (outer, nested)
}

#[test]
fn physical_parent_must_belong_to_declared_semantic_parent() {
    let mut spans = producer("nested_agent_owner_isolation");
    let (_, nested_owner) = outer_and_nested_owners(&spans);
    let unrelated_tool = spans[operation(&spans, "tool")]["span_id"].clone();
    spans[nested_owner].insert("parent_span_id".to_string(), unrelated_tool);

    let detail = detail(&spans, nested_owner);

    assert_eq!(detail.integrity.status, IntegrityStatus::Partial);
    assert_eq!(detail.parent_executable, None);
    assert!(codes(&detail).contains("parent_executable_correspondence_mismatch"));
}

#[test]
fn owned_tool_may_physically_interpose_declared_agent_parent() {
    let mut spans = producer("nested_agent_owner_isolation");
    let (outer_owner, nested_owner) = outer_and_nested_owners(&spans);
    let owned_tool = spans[operation(&spans, "tool")]["span_id"].clone();
    let outer_span_id = spans[outer_owner]["span_id"].clone();
    let outer_identity: Vec<(String, Json)> = ["definition_id", "runtime_id", "structural_id"]
        .iter()
        .map(|suffix| {
            (
                format!("junjo.parent_executable_{suffix}"),
                attribute(&spans[outer_owner], &format!("junjo.executable_{suffix}")).clone(),
            )
        })
        .collect();
    spans[nested_owner].insert("parent_span_id".to_string(), owned_tool.clone());
    let nested_attributes = attributes(&mut spans[nested_owner]);
    nested_attributes.insert("junjo.parent_executable_type".to_string(), json!("agent"));
    nested_attributes.extend(outer_identity);

    let detail = detail(&spans, nested_owner);

    assert_eq!(
        detail.integrity.status,
        IntegrityStatus::Complete,
        "{:?}",
        codes(&detail)
    );
    let parent = detail.parent_executable.expect("a parent executable");
    assert_eq!(parent.executable_type, ExecutableType::Agent);
    assert_eq!(json!(parent.span_id), outer_span_id);
    assert_eq!(json!(parent.physical_parent_span_id), owned_tool);
}
