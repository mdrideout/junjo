//! Conformance tests for authoritative Workflow Store diagnostics.

mod common;

use junjo_evidence::json::JsonObject;
use junjo_evidence::store_diagnostics::schemas::{IntegrityStatus, ReconstructionStatus};
use junjo_evidence::workflow_diagnostics::{
    WorkflowEvidenceErrorCode, WorkflowStoreDiagnostic, assemble_workflow_store_diagnostic,
};
use serde_json::json;

/// Every Workflow and Subflow owner in the canonical fixtures, as
/// `(case name, fixture spans, owner index)`.
fn workflow_cases() -> Vec<(String, Vec<JsonObject>, usize)> {
    let mut cases = Vec::new();
    for path in common::json_files(&common::fixture_root().join("workflow")) {
        let fixture = common::read_json(&path);
        let spans: Vec<JsonObject> = common::spans(&fixture).into_iter().cloned().collect();
        for (index, owner) in spans.iter().enumerate() {
            if matches!(common::span_type(owner), Some("workflow" | "subflow")) {
                let span_id = owner["span_id"].as_str().unwrap();
                cases.push((
                    format!("{}:{span_id}", common::file_stem(&path)),
                    spans.clone(),
                    index,
                ));
            }
        }
    }
    cases
}

fn assemble(spans: &[JsonObject], owner: usize) -> WorkflowStoreDiagnostic {
    let references: Vec<&JsonObject> = spans.iter().collect();
    assemble_workflow_store_diagnostic(references[owner], &references, None)
        .expect("the owner produces a projection")
}

fn codes(detail: &WorkflowStoreDiagnostic) -> Vec<&str> {
    detail
        .integrity
        .diagnostics
        .iter()
        .map(|issue| issue.code.as_str())
        .collect()
}

fn basic_workflow() -> (Vec<JsonObject>, usize) {
    let (_, spans, owner) = workflow_cases()
        .into_iter()
        .find(|(name, _, _)| name.starts_with("basic_workflow_success:"))
        .expect("the basic workflow fixture");
    (spans, owner)
}

fn attributes(span: &mut JsonObject) -> &mut JsonObject {
    span["attributes_json"].as_object_mut().unwrap()
}

#[test]
fn every_canonical_workflow_store_is_backend_verified() {
    let cases = workflow_cases();
    assert!(!cases.is_empty());
    for (name, spans, owner) in cases {
        let detail = assemble(&spans, owner);
        assert_eq!(
            detail.state.reconstruction_status,
            ReconstructionStatus::Verified,
            "{name}"
        );
        assert!(detail.state.reconstructable, "{name}");
        assert_eq!(detail.integrity.status, IntegrityStatus::Complete, "{name}");
        assert!(detail.integrity.diagnostics.is_empty(), "{name}");
    }
}

#[test]
fn workflow_store_unsafe_scalar_becomes_partial_not_unsafe_json() {
    let (_, mut spans, owner) = workflow_cases().remove(0);
    attributes(&mut spans[owner]).insert(
        "junjo.store.revision.end".to_string(),
        json!(9_007_199_254_740_992_i64),
    );
    let detail = assemble(&spans, owner);
    assert_eq!(detail.integrity.status, IntegrityStatus::Partial);
    assert_eq!(detail.state.revision_end, None);
    assert!(codes(&detail).contains(&"invalid_store_owner_fact"));
}

#[test]
fn workflow_store_excessive_payload_nesting_is_typed_partial_evidence() {
    let (_, mut spans, owner) = workflow_cases().remove(0);
    let nested = format!("{}\"leaf\"{}", "[".repeat(130), "]".repeat(130));
    attributes(&mut spans[owner]).insert("junjo.workflow.state.start".to_string(), json!(nested));
    let detail = assemble(&spans, owner);
    assert_eq!(detail.integrity.status, IntegrityStatus::Partial);
    assert!(codes(&detail).contains(&"payload_nesting_too_deep"));
}

#[test]
fn workflow_store_excludes_child_evidence_without_active_contract() {
    for (version, expected_code) in [
        (Some(1), "unsupported_contract"),
        (None, "missing_contract_version"),
    ] {
        let (mut spans, owner) = basic_workflow();
        let child = spans
            .iter()
            .position(|span| span["name"] == "fetch_input")
            .expect("the fetch_input span");
        match version {
            Some(version) => {
                attributes(&mut spans[child]).insert(
                    "junjo.telemetry.contract_version".to_string(),
                    json!(version),
                );
            }
            None => {
                attributes(&mut spans[child]).shift_remove("junjo.telemetry.contract_version");
            }
        }
        let child_span_id = spans[child]["span_id"].as_str().unwrap().to_string();

        let detail = assemble(&spans, owner);

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
                .all(|transition| transition.span_id != child_span_id)
        );
        assert!(codes(&detail).contains(&expected_code), "{expected_code}");
    }
}

#[test]
fn workflow_store_excludes_transition_on_noncanonical_carrier_span() {
    let (mut spans, owner) = basic_workflow();
    let carrier = spans
        .iter()
        .enumerate()
        .position(|(index, span)| {
            index != owner
                && span["events_json"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .any(|event| event["name"] == "set_state")
        })
        .expect("a span that carries a Store transition");
    spans[carrier].insert("span_id".to_string(), json!("not-a-span-id"));

    let detail = assemble(&spans, owner);

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
    assert!(codes(&detail).contains(&"invalid_span_id"));
}

#[test]
fn spans_that_are_not_workflow_owners_are_rejected() {
    let (mut spans, owner) = basic_workflow();
    attributes(&mut spans[owner]).insert("junjo.span_type".to_string(), json!("node"));
    let references: Vec<&JsonObject> = spans.iter().collect();
    let error =
        assemble_workflow_store_diagnostic(references[owner], &references, None).unwrap_err();
    assert_eq!(
        error.code,
        WorkflowEvidenceErrorCode::UnidentifiableWorkflow
    );
    assert!(error.diagnostics.is_empty());
}

#[test]
fn an_owner_without_the_active_contract_is_unsupported() {
    let (mut spans, owner) = basic_workflow();
    attributes(&mut spans[owner]).insert("junjo.telemetry.contract_version".to_string(), json!(1));
    let references: Vec<&JsonObject> = spans.iter().collect();
    let error =
        assemble_workflow_store_diagnostic(references[owner], &references, None).unwrap_err();
    assert_eq!(error.code, WorkflowEvidenceErrorCode::UnsupportedContract);
    assert_eq!(error.message, "Expected telemetry contract 3; observed 1.");
    assert_eq!(error.diagnostics[0].code, "unsupported_contract");
}

#[test]
fn an_owner_without_usable_identity_is_unidentifiable() {
    let (mut spans, owner) = basic_workflow();
    spans[owner].insert("name".to_string(), json!(""));
    let references: Vec<&JsonObject> = spans.iter().collect();
    let error =
        assemble_workflow_store_diagnostic(references[owner], &references, None).unwrap_err();
    assert_eq!(
        error.code,
        WorkflowEvidenceErrorCode::UnidentifiableWorkflow
    );
    assert_eq!(error.diagnostics[0].code, "required_identity_missing");

    let (mut spans, owner) = basic_workflow();
    spans[owner].insert("trace_id".to_string(), json!("not-a-trace-id"));
    let references: Vec<&JsonObject> = spans.iter().collect();
    let error =
        assemble_workflow_store_diagnostic(references[owner], &references, None).unwrap_err();
    assert_eq!(
        error.code,
        WorkflowEvidenceErrorCode::UnidentifiableWorkflow
    );
    assert_eq!(error.diagnostics[0].code, "invalid_workflow_projection");
}
