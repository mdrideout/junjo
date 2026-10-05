//! The committed projection files, and their generator.
//!
//! Three files hold what the assemblers produce from the valid telemetry
//! fixtures. The frontend's tests read them, so the frontend is tested against
//! real backend output without running a backend:
//!
//! - `tests/generated/agent_semantic_projections.json`, in this crate,
//! - `tests/generated/composable_store_trace.json`, in this crate, and
//! - `workflow-store-projections.json`, in the frontend's Workflow feature.
//!
//! The tests here fail when a file is not, text for text, what the assemblers
//! produce now. After a deliberate change, regenerate all three and review
//! the difference as a contract change:
//!
//! ```bash
//! JUNJO_REGENERATE_PROJECTIONS=1 cargo test -p junjo-evidence --test generated_projections
//! ```

mod common;

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use junjo_evidence::agent_diagnostics::assembler::assemble_agent_detail;
use junjo_evidence::json::{Json, JsonObject};
use junjo_evidence::trace_evidence::assembler::assemble_trace_evidence;
use junjo_evidence::trace_evidence::schemas::TraceEvidence;
use junjo_evidence::workflow_diagnostics::assemble_workflow_store_diagnostic;
use serde_json::json;

const REGENERATE: &str = "JUNJO_REGENERATE_PROJECTIONS";

fn agent_projections_path() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/generated/agent_semantic_projections.json")
}

fn composable_store_trace_path() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/generated/composable_store_trace.json")
}

fn workflow_projections_path() -> PathBuf {
    common::repository_root().join(
        "apps/studio/frontend/src/features/workflow-executions/testing/\
         workflow-store-projections.json",
    )
}

/// One projection per Agent owner span of every valid producer and consumer
/// fixture. A fixture with several Agents numbers them in span order.
fn agent_projections() -> Vec<Json> {
    let agent = common::fixture_root().join("agent");
    let mut paths = common::json_files(&agent.join("producer"));
    paths.extend(common::json_files(&agent.join("consumer")));
    paths.sort();

    let mut projections = Vec::new();
    for path in paths {
        let fixture = common::read_json(&path);
        let spans = common::spans(&fixture);
        let owners: Vec<&JsonObject> = spans
            .iter()
            .copied()
            .filter(|span| common::span_type(span) == Some("agent"))
            .collect();
        let scenario = fixture["scenario"].as_str().expect("a scenario name");
        for (position, owner) in owners.iter().enumerate() {
            let detail = assemble_agent_detail(owner, &spans, None)
                .unwrap_or_else(|error| panic!("{scenario}: a detail, not {error:?}"));
            let case_name = if owners.len() == 1 {
                scenario.to_string()
            } else {
                format!("{scenario}__agent_{}", position + 1)
            };
            projections.push(json!({
                "case_name": case_name,
                "summary": detail.summary,
                "detail": detail,
            }));
        }
    }
    projections
}

/// One projection per Workflow and Subflow owner span of every Workflow
/// fixture, named by the fixture and the owner's span.
fn workflow_projections() -> Vec<Json> {
    let mut projections = Vec::new();
    for path in common::json_files(&common::fixture_root().join("workflow")) {
        let fixture = common::read_json(&path);
        let spans = common::spans(&fixture);
        for owner in &spans {
            if !matches!(common::span_type(owner), Some("workflow" | "subflow")) {
                continue;
            }
            let span_id = owner["span_id"].as_str().expect("a span identifier");
            let detail = assemble_workflow_store_diagnostic(owner, &spans, None)
                .unwrap_or_else(|error| panic!("{span_id}: a projection, not {error:?}"));
            projections.push(json!({
                "case_name": format!("{}:{span_id}", common::file_stem(&path)),
                "detail": detail,
            }));
        }
    }
    projections
}

/// The trace evidence of the shared application Store fixture: an Agent that
/// lends the Store it borrowed to a nested Workflow.
fn composable_store_trace() -> TraceEvidence {
    let fixture = common::read_json(
        &common::fixture_root().join("agent/producer/shared_application_store.json"),
    );
    let trace_id = fixture["trace_id"].as_str().expect("a trace identifier");
    let spans = serde_json::from_value(fixture["spans"].clone()).expect("normalized spans");
    assemble_trace_evidence(trace_id, spans)
}

/// The file text of one trace's evidence: members in the order the backend
/// serializes them, two-space indentation, and a final newline.
fn render_trace(evidence: &TraceEvidence) -> String {
    let mut text = serde_json::to_string_pretty(evidence).expect("trace evidence serializes");
    text.push('\n');
    text
}

/// The file text of a projection list: cases in name order, object members
/// in name order, two-space indentation, and a final newline.
fn render(mut projections: Vec<Json>) -> String {
    projections.sort_by(|left, right| left["case_name"].as_str().cmp(&right["case_name"].as_str()));
    let mut document = Json::Array(projections);
    document.sort_all_objects();
    let mut text = serde_json::to_string_pretty(&document).expect("projections serialize");
    text.push('\n');
    text
}

/// Write the file when regeneration is asked for. Otherwise prove the
/// committed file is exactly `rendered`.
fn write_or_prove_current(path: &Path, rendered: &str) {
    if std::env::var_os(REGENERATE).is_some() {
        std::fs::create_dir_all(path.parent().expect("a parent directory"))
            .unwrap_or_else(|error| panic!("cannot create {}: {error}", path.display()));
        std::fs::write(path, rendered)
            .unwrap_or_else(|error| panic!("cannot write {}: {error}", path.display()));
        return;
    }
    let committed = std::fs::read_to_string(path)
        .unwrap_or_else(|error| panic!("cannot read {}: {error}", path.display()));
    assert!(
        committed == rendered,
        "{} is not what the assemblers produce now. If the change is intended, regenerate it \
         with {REGENERATE}=1 and review the difference.",
        path.display()
    );
}

fn case_names(projections: &[Json]) -> BTreeSet<&str> {
    projections
        .iter()
        .map(|projection| projection["case_name"].as_str().expect("a case name"))
        .collect()
}

#[test]
fn the_agent_projection_file_is_current() {
    let projections = agent_projections();
    // Every owner has its own case: no name is produced twice.
    assert_eq!(case_names(&projections).len(), projections.len());
    assert!(!projections.is_empty());
    write_or_prove_current(&agent_projections_path(), &render(projections));
}

#[test]
fn the_composable_store_trace_file_is_current() {
    let evidence = composable_store_trace();
    assert!(!evidence.executables_by_span_id.is_empty());
    write_or_prove_current(&composable_store_trace_path(), &render_trace(&evidence));
}

#[test]
fn the_workflow_store_projection_file_is_current() {
    let projections = workflow_projections();
    assert_eq!(case_names(&projections).len(), projections.len());
    assert!(!projections.is_empty());
    write_or_prove_current(&workflow_projections_path(), &render(projections));
}
