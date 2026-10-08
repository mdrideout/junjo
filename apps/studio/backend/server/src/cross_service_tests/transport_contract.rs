//! The telemetry contract through the whole transport path.
//!
//! Every valid shared fixture is sent to ingestion over OTLP and read back
//! through the span repository at each stage of its life in storage:
//!
//! 1. unflushed, in the hot snapshot,
//! 2. flushed to a cold file the indexer has not reached, and
//! 3. indexed.
//!
//! At every stage the backend must return the fixture's spans unchanged.

use junjo_evidence::agent_diagnostics::assembler::assemble_agent_detail;
use junjo_evidence::agent_diagnostics::schemas::{AgentEvidenceError, AgentExecutionDetail};
use junjo_evidence::json::{Json, JsonObject};

use super::{harness, otlp};
use crate::db::metadata;
use crate::features::otel_spans::repository;
use crate::features::span_ingestion::IngestionClient;
use crate::state::AppState;
use crate::test_support::{INTERNAL_TOKEN, api_spans, case_spans, telemetry_fixtures};

/// A page size larger than any fixture.
const LARGE_PAGE: usize = 250;

/// Every valid fixture: the Workflow scenarios and the Agent producer and
/// consumer scenarios, named with their directory so no two share a name.
fn valid_fixtures() -> Vec<(String, Json)> {
    let mut fixtures = Vec::new();
    for directory in ["workflow", "agent/producer", "agent/consumer"] {
        for (name, case) in telemetry_fixtures(directory) {
            fixtures.push((format!("{directory}/{name}"), case));
        }
    }
    fixtures
}

/// The detail of every Agent execution in one trace, in the order of the
/// owner spans' identifiers. Each detail is assembled from the whole trace.
fn agent_details(trace: &[JsonObject]) -> Vec<Result<AgentExecutionDetail, AgentEvidenceError>> {
    let trace: Vec<&JsonObject> = trace.iter().collect();
    let mut owners: Vec<&JsonObject> = trace
        .iter()
        .copied()
        .filter(|span| span["attributes_json"]["junjo.span_type"] == "agent")
        .collect();
    owners.sort_by(|left, right| left["span_id"].as_str().cmp(&right["span_id"].as_str()));
    owners
        .into_iter()
        .map(|owner| assemble_agent_detail(owner, &trace, None))
        .collect()
}

/// The indexed cold files that contain a trace.
async fn indexed_files(state: &AppState, trace_id: &str) -> Vec<String> {
    let trace_id = trace_id.to_string();
    state
        .metadata
        .call(move |connection| metadata::file_paths_for_trace(connection, &trace_id))
        .await
        .unwrap()
}

/// Assert that the backend serves one fixture unchanged: its trace, the
/// Agent details assembled from that trace, its Workflow spans, and its Agent
/// spans.
async fn assert_served_unchanged(state: &AppState, case: &Json, stage: &str) {
    let trace_id = case["trace_id"].as_str().unwrap();
    let service_name = case["service_name"].as_str().unwrap();

    let trace = repository::trace_spans(state, trace_id).await.unwrap();
    assert_eq!(
        api_spans(&trace),
        case_spans(case, None),
        "{stage}: trace spans"
    );

    let served_trace: Vec<JsonObject> = trace
        .iter()
        .map(|span| span.to_evidence().to_object())
        .collect();
    let fixture_trace: Vec<JsonObject> = case["spans"]
        .as_array()
        .unwrap()
        .iter()
        .map(|span| span.as_object().unwrap().clone())
        .collect();
    assert_eq!(
        agent_details(&served_trace),
        agent_details(&fixture_trace),
        "{stage}: Agent details"
    );

    let workflows = repository::workflow_spans(state, service_name, LARGE_PAGE, None)
        .await
        .unwrap();
    assert_eq!(
        api_spans(&workflows),
        case_spans(case, Some("workflow")),
        "{stage}: Workflow spans"
    );

    let agents = repository::agent_spans(state, service_name).await.unwrap();
    assert_eq!(
        api_spans(&agents),
        case_spans(case, Some("agent")),
        "{stage}: Agent spans"
    );
}

#[tokio::test]
async fn every_valid_fixture_is_served_unchanged_while_unflushed_flushed_and_indexed() {
    let (mut app, ingestion) = harness::start().await;
    let indexer = app.spawn_indexer();
    // The same application without ingestion. Its queries read only the cold
    // files the metadata index selects. Port 9 (discard) is not listening.
    let index_only = AppState {
        ingestion: IngestionClient::new("127.0.0.1", 9, INTERNAL_TOKEN).unwrap(),
        ..app.state.clone()
    };

    // The fixtures share the process: each has its own trace and service, and
    // each is flushed before the next is sent.
    for (name, case) in valid_fixtures() {
        let trace_id = case["trace_id"].as_str().unwrap();
        ingestion.export(otlp::fixture_export_request(&case)).await;

        let unflushed = app.state.ingestion.query_context().await;
        assert!(unflushed.hot_snapshot_path.is_some(), "{name}");
        assert_served_unchanged(&app.state, &case, &format!("{name}, unflushed")).await;

        assert_eq!(app.state.ingestion.flush_wal().await, Ok(()), "{name}");
        let flushed = app.state.ingestion.query_context().await;
        assert_eq!(flushed.hot_snapshot_path, None, "{name}");
        assert_eq!(
            indexed_files(&app.state, trace_id).await,
            Vec::<String>::new(),
            "{name}"
        );
        assert_served_unchanged(&app.state, &case, &format!("{name}, flushed")).await;

        // The indexer finds the one new file, under the path ingestion
        // reported for it.
        assert_eq!(app.state.indexer.index_now().await, Ok(1), "{name}");
        let indexed = indexed_files(&app.state, trace_id).await;
        assert_eq!(indexed.len(), 1, "{name}");
        assert!(
            flushed.recent_cold_paths.contains(&indexed[0]),
            "{name}: {indexed:?} is not among {:?}",
            flushed.recent_cold_paths
        );
        // Ingestion still reports the file as recently flushed. It is read
        // once.
        assert_served_unchanged(&app.state, &case, &format!("{name}, indexed")).await;
        assert_served_unchanged(&index_only, &case, &format!("{name}, from the index alone")).await;
    }

    (indexer.shutdown_sender())();
    indexer.finished.await.unwrap();
}
