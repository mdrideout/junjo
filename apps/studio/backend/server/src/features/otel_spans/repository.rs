//! Span selection across the two tiers.
//!
//! Every function here answers one question about stored spans by combining
//! three sources (ingestion ADR-002):
//!
//! 1. ingestion's hot snapshot and its list of recently flushed cold files,
//! 2. the indexed cold files the metadata index selects, and
//! 3. one DataFusion query over those files.
//!
//! When the snapshot call fails, a query degrades to indexed cold data instead
//! of failing.
//!
//! Ingestion writes the hot snapshot to one path, replaces it for the first
//! request after its reuse period, and removes it when its log is empty.
//! Queries run concurrently, so a query can be reading the snapshot when
//! another request has it replaced. A query that fails after that asks
//! ingestion again and runs once more over what ingestion names then.

use std::collections::{BTreeSet, HashSet};
use std::time::SystemTime;

use datafusion::error::DataFusionError;

use super::query::{QuerySources, Span, SpanQuery};
use super::{
    MAX_RECENT_COLD_FILES_FOR_SERVICE_DISCOVERY, MAX_RECENT_COLD_FILES_PER_QUERY,
    augment_with_recent_cold_files,
};
use crate::db::metadata;
use crate::error::ApiError;
use crate::state::AppState;

/// Upper bound on indexed cold files registered for one service listing,
/// newest first. It keeps query memory proportional to the request instead of
/// to a service's whole cold history.
const MAX_COLD_FILES_PER_SERVICE_QUERY: usize = 20;

/// An LLM-filtered page examines this many recent root spans per requested
/// result, up to the cap. Root spans are selected before their traces are
/// known to contain LLM spans, so the window is wider than the page.
const LLM_ROOT_SPAN_CANDIDATES_PER_RESULT: usize = 5;
const MAX_LLM_ROOT_SPAN_CANDIDATES: usize = 5000;

/// The files one span query reads: the indexed cold files the query needs,
/// the recent-cold bridge, and the hot snapshot. Ingestion is asked every
/// time.
///
/// The index is read first and ingestion is asked last, so its answer is as
/// new as it can be when the files are opened. A flush and a rebuilt
/// snapshot that land after the answer leave the query with a snapshot that
/// no longer holds the flushed spans and without the file that does.
async fn select_sources(state: &AppState, query: SpanQuery<'_>) -> Result<QuerySources, ApiError> {
    // `None` reads every recent cold file.
    let (indexed, recent_cold_limit) = match query {
        // The files that contain the trace.
        SpanQuery::Trace { trace_id } | SpanQuery::Span { trace_id, .. } => {
            let lookup = trace_id.to_string();
            let indexed = state
                .metadata
                .call(move |connection| metadata::file_paths_for_trace(connection, &lookup))
                .await?;
            (indexed, Some(MAX_RECENT_COLD_FILES_PER_QUERY))
        }
        // The service's newest files. The metadata index selects files by
        // service only. DataFusion decides which spans in them are roots.
        SpanQuery::Service { service_name, .. } | SpanQuery::Roots { service_name, .. } => {
            let lookup = service_name.to_string();
            let indexed = state
                .metadata
                .call(move |connection| {
                    metadata::file_paths_for_service(
                        connection,
                        &lookup,
                        Some(MAX_COLD_FILES_PER_SERVICE_QUERY),
                    )
                })
                .await?;
            (indexed, Some(MAX_RECENT_COLD_FILES_PER_QUERY))
        }
        // The service's newest files with Workflow spans.
        SpanQuery::Workflows { service_name, .. } => {
            let lookup = service_name.to_string();
            let indexed = state
                .metadata
                .call(move |connection| {
                    metadata::workflow_file_paths(
                        connection,
                        &lookup,
                        MAX_COLD_FILES_PER_SERVICE_QUERY,
                    )
                })
                .await?;
            (indexed, Some(MAX_RECENT_COLD_FILES_PER_QUERY))
        }
        // Agent semantic filters are applied to the result, so nothing is cut
        // off here: every indexed file with Agent spans for the service is
        // read, and every recent-cold file.
        SpanQuery::Agents { service_name } => {
            let lookup = service_name.to_string();
            let indexed = state
                .metadata
                .call(move |connection| metadata::agent_file_paths(connection, &lookup))
                .await?;
            (indexed, None)
        }
        // An identity must resolve wherever its span is stored, so every
        // indexed file of the service is read, and every recent-cold file.
        SpanQuery::Executable { service_name, .. } => {
            let lookup = service_name.to_string();
            let indexed = state
                .metadata
                .call(move |connection| metadata::file_paths_for_service(connection, &lookup, None))
                .await?;
            (indexed, None)
        }
    };
    let ingestion = state.ingestion.query_context().await;
    Ok(QuerySources {
        cold_files: augment_with_recent_cold_files(
            indexed,
            &ingestion.recent_cold_paths,
            recent_cold_limit.unwrap_or(ingestion.recent_cold_paths.len()),
        ),
        hot_snapshot: ingestion.hot_snapshot_path,
    })
}

/// The hot snapshot file's length and modification time. `None` when a query
/// has no hot snapshot or the file is gone.
type SnapshotIdentity = Option<(u64, SystemTime)>;

fn snapshot_identity(sources: &QuerySources) -> SnapshotIdentity {
    let metadata = std::fs::metadata(sources.hot_snapshot.as_deref()?).ok()?;
    Some((metadata.len(), metadata.modified().ok()?))
}

/// Whether a failed query may run again: ingestion replaced or removed the
/// hot snapshot after naming it.
///
/// `handed` is the snapshot's identity when the query started. A snapshot
/// that was already gone then has no identity, and counts as removed. A query
/// that ran out of memory is not run again.
fn snapshot_changed(
    sources: &QuerySources,
    handed: SnapshotIdentity,
    error: &DataFusionError,
) -> bool {
    sources.hot_snapshot.is_some()
        && !matches!(error.find_root(), DataFusionError::ResourcesExhausted(_))
        && (handed.is_none() || snapshot_identity(sources) != handed)
}

fn log_snapshot_change(error: &DataFusionError) {
    tracing::warn!(
        %error,
        "the hot snapshot changed while it was read; asking ingestion again"
    );
}

/// Whether a trace query that found nothing may run again: ingestion
/// replaced or removed the hot snapshot while the query ran.
///
/// A query can read a rebuilt snapshot without failing. If a flush came
/// before the rebuild, the trace's spans are in a cold file the query was
/// not given, and a trace that was just listed looks as if it did not exist.
/// Only a trace or span query shows that: a listing cannot tell that spans
/// are missing.
fn found_nothing_under_a_changed_snapshot(
    query: SpanQuery<'_>,
    spans: &[Span],
    sources: &QuerySources,
    handed: SnapshotIdentity,
) -> bool {
    spans.is_empty()
        && matches!(query, SpanQuery::Trace { .. } | SpanQuery::Span { .. })
        && sources.hot_snapshot.is_some()
        && snapshot_identity(sources) != handed
}

/// Select a query's files and run it.
async fn run_query(state: &AppState, query: SpanQuery<'_>) -> Result<Vec<Span>, ApiError> {
    let sources = select_sources(state, query).await?;
    let handed = snapshot_identity(&sources);
    let result = match state.query.run(&sources, query).await {
        Err(error) if snapshot_changed(&sources, handed, &error) => {
            log_snapshot_change(&error);
            let sources = select_sources(state, query).await?;
            state.query.run(&sources, query).await
        }
        Ok(spans) if found_nothing_under_a_changed_snapshot(query, &spans, &sources, handed) => {
            tracing::warn!(
                ?query,
                "the hot snapshot changed while a trace was read and nothing was found; \
                 asking ingestion again"
            );
            let sources = select_sources(state, query).await?;
            state.query.run(&sources, query).await
        }
        result => result,
    };
    result.map_err(|error| {
        tracing::error!(%error, ?query, "two-tier span query failed");
        ApiError::internal()
    })
}

/// Distinct service names across both tiers, alphabetically.
///
/// Cold-tier names come from the metadata index, never from scanning cold
/// Parquet. Recent-cold files and the hot snapshot are queried once together.
pub async fn distinct_service_names(state: &AppState) -> Result<Vec<String>, ApiError> {
    let cold_services = state
        .metadata
        .call(|connection| metadata::services(connection))
        .await?;
    let mut services: BTreeSet<String> = cold_services.into_iter().collect();
    services.extend(unindexed_service_names(state).await);
    Ok(services.into_iter().collect())
}

/// The recent-cold files and the hot snapshot that service discovery reads.
async fn service_discovery_sources(state: &AppState) -> QuerySources {
    let ingestion = state.ingestion.query_context().await;
    QuerySources {
        cold_files: ingestion
            .recent_cold_paths
            .into_iter()
            .take(MAX_RECENT_COLD_FILES_FOR_SERVICE_DISCOVERY)
            .collect(),
        hot_snapshot: ingestion.hot_snapshot_path,
    }
}

/// The service names in spans the metadata index does not cover yet.
///
/// A query failure is logged and adds nothing: the caller still has the
/// metadata index's cold-tier services.
async fn unindexed_service_names(state: &AppState) -> Vec<String> {
    let sources = service_discovery_sources(state).await;
    if sources.cold_files.is_empty() && sources.hot_snapshot.is_none() {
        return Vec::new();
    }
    let handed = snapshot_identity(&sources);
    let names = match state.query.distinct_service_names(&sources).await {
        Err(error) if snapshot_changed(&sources, handed, &error) => {
            log_snapshot_change(&error);
            let sources = service_discovery_sources(state).await;
            state.query.distinct_service_names(&sources).await
        }
        names => names,
    };
    names.unwrap_or_else(|error| {
        tracing::error!(%error, "failed to query distinct service names");
        Vec::new()
    })
}

/// The newest spans of one service.
pub async fn service_spans(
    state: &AppState,
    service_name: &str,
    limit: usize,
) -> Result<Vec<Span>, ApiError> {
    let query = SpanQuery::Service {
        service_name,
        limit,
    };
    run_query(state, query).await
}

/// The newest root spans of one service.
pub async fn root_spans(
    state: &AppState,
    service_name: &str,
    limit: usize,
) -> Result<Vec<Span>, ApiError> {
    let query = SpanQuery::Roots {
        service_name,
        limit,
    };
    run_query(state, query).await
}

/// The newest root spans of one service whose traces contain an LLM span.
///
/// A bounded window of recent root spans is selected first. Their traces are
/// then checked against the metadata index, which knows a trace's LLM spans
/// once their file is indexed, and against the spans the index does not cover
/// yet: the hot snapshot and the flushed files the indexer has not reached
/// (ingestion ADR-002).
pub async fn root_spans_with_llm(
    state: &AppState,
    service_name: &str,
    limit: usize,
) -> Result<Vec<Span>, ApiError> {
    let error = match llm_root_spans(state, service_name, limit).await? {
        Ok(root_spans) => return Ok(root_spans),
        Err(error) => error,
    };
    log_snapshot_change(&error);
    llm_root_spans(state, service_name, limit)
        .await?
        .map_err(|error| unindexed_llm_query_failed(&error, service_name))
}

/// One attempt at the LLM listing.
///
/// The listing reads the hot snapshot twice: for the root spans, and again to
/// classify the spans the index does not cover. The inner error is a second
/// read that failed because ingestion replaced or removed the snapshot under
/// it. The whole listing may then be attempted again.
async fn llm_root_spans(
    state: &AppState,
    service_name: &str,
    limit: usize,
) -> Result<Result<Vec<Span>, DataFusionError>, ApiError> {
    let candidate_limit = limit
        .saturating_mul(LLM_ROOT_SPAN_CANDIDATES_PER_RESULT)
        .min(MAX_LLM_ROOT_SPAN_CANDIDATES);
    let query = SpanQuery::Roots {
        service_name,
        limit: candidate_limit,
    };
    let mut root_spans = run_query(state, query).await?;
    let candidate_trace_ids: HashSet<String> = root_spans
        .iter()
        .filter(|span| !span.trace_id.is_empty())
        .map(|span| span.trace_id.clone())
        .collect();
    if candidate_trace_ids.is_empty() {
        return Ok(Ok(Vec::new()));
    }

    // Ingestion is asked again for the second read. A flush between the two
    // reads moves unflushed spans into a file the first answer did not name,
    // and a rebuilt snapshot no longer holds them. This answer names that
    // file. No other query asks twice: ingestion ADR-002 records the cost.
    let ingestion = state.ingestion.query_context().await;
    let recent_cold_files: Vec<String> = ingestion
        .recent_cold_paths
        .into_iter()
        .take(MAX_RECENT_COLD_FILES_PER_QUERY)
        .collect();
    let lookup_service = service_name.to_string();
    let lookup_trace_ids = candidate_trace_ids.clone();
    let (unindexed_cold_files, mut llm_trace_ids) = state
        .metadata
        .call(move |connection| {
            // The unindexed files are found first. A file that is indexed
            // between the two lookups is then read below and found in the
            // index as well. In the other order both could miss it.
            let unindexed = metadata::unindexed_file_paths(connection, &recent_cold_files)?;
            let llm =
                metadata::filter_llm_trace_ids(connection, &lookup_service, &lookup_trace_ids)?;
            Ok((unindexed, llm))
        })
        .await?;
    let unindexed = QuerySources {
        cold_files: unindexed_cold_files,
        hot_snapshot: ingestion.hot_snapshot_path,
    };

    // Only the candidates the index has not resolved are looked for.
    let unresolved: HashSet<String> = candidate_trace_ids
        .difference(&llm_trace_ids)
        .cloned()
        .collect();
    if !unresolved.is_empty()
        && (unindexed.hot_snapshot.is_some() || !unindexed.cold_files.is_empty())
    {
        // No span of theirs starts before the oldest of their root spans.
        // Without a start time for every one of those roots there is no
        // such bound.
        let since_ns = root_spans
            .iter()
            .filter(|span| unresolved.contains(&span.trace_id))
            .map(|span| span.start_time_ns)
            .min()
            .flatten();
        let handed = snapshot_identity(&unindexed);
        match state
            .query
            .unindexed_llm_trace_ids(&unindexed, service_name, &unresolved, since_ns)
            .await
        {
            Ok(unindexed_llm_trace_ids) => llm_trace_ids.extend(unindexed_llm_trace_ids),
            Err(error) if snapshot_changed(&unindexed, handed, &error) => return Ok(Err(error)),
            Err(error) => return Err(unindexed_llm_query_failed(&error, service_name)),
        }
    }

    root_spans.retain(|span| llm_trace_ids.contains(&span.trace_id));
    root_spans.truncate(limit);
    Ok(Ok(root_spans))
}

fn unindexed_llm_query_failed(error: &DataFusionError, service_name: &str) -> ApiError {
    tracing::error!(%error, service_name, "unindexed LLM trace query failed");
    ApiError::internal()
}

/// The newest Workflow spans of one service.
pub async fn workflow_spans(
    state: &AppState,
    service_name: &str,
    limit: usize,
) -> Result<Vec<Span>, ApiError> {
    let query = SpanQuery::Workflows {
        service_name,
        limit,
    };
    run_query(state, query).await
}

/// Every Agent span of one service, newest first.
pub async fn agent_spans(state: &AppState, service_name: &str) -> Result<Vec<Span>, ApiError> {
    run_query(state, SpanQuery::Agents { service_name }).await
}

/// The spans of one service that are the executable with exactly this type
/// and runtime identity. Evidence is not interpreted here.
pub async fn executable_spans(
    state: &AppState,
    service_name: &str,
    executable_type: &str,
    runtime_id: &str,
) -> Result<Vec<Span>, ApiError> {
    let query = SpanQuery::Executable {
        service_name,
        executable_type,
        runtime_id,
    };
    run_query(state, query).await
}

/// Every span of one trace, newest first.
pub async fn trace_spans(state: &AppState, trace_id: &str) -> Result<Vec<Span>, ApiError> {
    run_query(state, SpanQuery::Trace { trace_id }).await
}

/// One span of one trace, or nothing when the trace has no such span.
pub async fn span(
    state: &AppState,
    trace_id: &str,
    span_id: &str,
) -> Result<Option<Span>, ApiError> {
    let spans = run_query(state, SpanQuery::Span { trace_id, span_id }).await?;
    Ok(spans.into_iter().next())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::{
        TestSpan, ingestion_reporting, ingestion_reporting_in_turn, test_app,
    };

    const SERVICE: &str = "checkout";
    /// A page size larger than any data these tests write.
    const LARGE_PAGE: usize = 250;
    /// GenAI semantic-convention attributes, as the xAI SDK emits them.
    const LLM_ATTRIBUTES: &str = r#"{"gen_ai.provider.name":"xai","gen_ai.operation.name":"chat"}"#;

    fn span_ids(spans: &[Span]) -> Vec<&str> {
        spans.iter().map(|span| span.span_id.as_str()).collect()
    }

    /// A root span named `<trace>-root`.
    fn root(trace_id: &str, start_time_ns: i64) -> TestSpan {
        TestSpan::new(trace_id, &format!("{trace_id}-root"), SERVICE)
            .times(start_time_ns, start_time_ns + 100)
    }

    /// An LLM span under the root of its trace.
    fn llm_child(trace_id: &str, start_time_ns: i64) -> TestSpan {
        TestSpan::new(trace_id, &format!("{trace_id}-llm"), SERVICE)
            .parent(&format!("{trace_id}-root"))
            .times(start_time_ns, start_time_ns + 100)
            .attributes(LLM_ATTRIBUTES)
    }

    /// The attributes of an executable owner span.
    fn executable(span_type: &str, runtime_id: &str) -> String {
        format!(
            r#"{{"junjo.span_type":"{span_type}","junjo.executable_runtime_id":"{runtime_id}"}}"#
        )
    }

    #[test]
    fn a_failed_query_runs_again_only_when_its_snapshot_was_replaced_or_removed() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("hot_snapshot.parquet");
        std::fs::write(&path, b"the snapshot ingestion named").unwrap();
        let sources = QuerySources {
            cold_files: Vec::new(),
            hot_snapshot: Some(path.to_str().unwrap().to_string()),
        };
        let handed = snapshot_identity(&sources);
        let failed = DataFusionError::Execution("a read failed".to_string());
        // The pool's error arrives wrapped in what the query was doing.
        let out_of_memory = DataFusionError::ResourcesExhausted("the pool is full".to_string())
            .context("while sorting");

        // The file is the one the query was given: the failure is not about
        // the snapshot.
        assert!(!snapshot_changed(&sources, handed, &failed));

        std::fs::write(&path, b"a newer snapshot").unwrap();
        assert!(snapshot_changed(&sources, handed, &failed));
        assert!(!snapshot_changed(&sources, handed, &out_of_memory));

        std::fs::remove_file(&path).unwrap();
        assert!(snapshot_changed(&sources, handed, &failed));
        // It was already gone when the query started.
        assert!(snapshot_changed(&sources, None, &failed));

        // A query without a hot snapshot has nothing that can change.
        assert!(!snapshot_changed(&QuerySources::default(), None, &failed));
    }

    #[test]
    fn a_trace_query_that_found_nothing_runs_again_only_when_its_snapshot_changed() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("hot_snapshot.parquet");
        std::fs::write(&path, b"the snapshot ingestion named").unwrap();
        let sources = QuerySources {
            cold_files: Vec::new(),
            hot_snapshot: Some(path.to_str().unwrap().to_string()),
        };
        let handed = snapshot_identity(&sources);
        let trace = SpanQuery::Trace {
            trace_id: "trace-1",
        };
        let span = SpanQuery::Span {
            trace_id: "trace-1",
            span_id: "span-1",
        };
        let listing = SpanQuery::Roots {
            service_name: SERVICE,
            limit: 50,
        };
        let again = |query, sources: &QuerySources| {
            found_nothing_under_a_changed_snapshot(query, &[], sources, handed)
        };

        // The snapshot is the one the query was given: the trace is unknown.
        assert!(!again(trace, &sources));

        std::fs::write(&path, b"a newer snapshot").unwrap();
        assert!(again(trace, &sources));
        assert!(again(span, &sources));
        // An empty listing does not say that spans are missing.
        assert!(!again(listing, &sources));

        std::fs::remove_file(&path).unwrap();
        assert!(again(trace, &sources));
        // No hot snapshot was named: there is nothing that can change.
        assert!(!again(trace, &QuerySources::default()));
    }

    /// Ingestion names a snapshot, then flushes its log and removes the
    /// snapshot before the query reads it. The next answer names the cold
    /// file the spans went to.
    #[tokio::test]
    async fn a_query_whose_snapshot_is_gone_asks_ingestion_again() {
        let mut app = test_app();
        let flushed = app.write_cold_file(
            "flushed.parquet",
            &[
                root("trace-1", 1_000),
                llm_child("trace-1", 1_010),
                TestSpan::new("trace-2", "span-2", "billing"),
            ],
        );
        let gone = app.write_hot_snapshot(&[]);
        std::fs::remove_file(&gone).unwrap();
        let before_the_flush: (Option<&str>, &[String]) = (Some(&gone), &[]);
        let after_the_flush: (Option<&str>, &[String]) = (None, std::slice::from_ref(&flushed));
        let answers = [before_the_flush, after_the_flush];

        app.state.ingestion = ingestion_reporting_in_turn(&answers).await;
        let trace = trace_spans(&app.state, "trace-1").await.unwrap();
        assert_eq!(span_ids(&trace), ["trace-1-llm", "trace-1-root"]);

        app.state.ingestion = ingestion_reporting_in_turn(&answers).await;
        let listed = root_spans(&app.state, SERVICE, LARGE_PAGE).await.unwrap();
        assert_eq!(span_ids(&listed), ["trace-1-root"]);

        app.state.ingestion = ingestion_reporting_in_turn(&answers).await;
        assert_eq!(
            distinct_service_names(&app.state).await.unwrap(),
            ["billing", SERVICE]
        );
    }

    #[tokio::test]
    async fn a_query_whose_snapshot_is_gone_twice_fails_and_service_discovery_uses_the_index() {
        let mut app = test_app();
        app.index_cold_file("a.parquet", &[root("trace-1", 1_000)]);
        let gone = app.write_hot_snapshot(&[]);
        std::fs::remove_file(&gone).unwrap();
        app.state.ingestion = ingestion_reporting(Some(&gone), &[]).await;

        // The spans the snapshot held are in a file this query does not know.
        // Answering from the indexed file alone would leave them out.
        assert!(trace_spans(&app.state, "trace-1").await.is_err());
        assert!(root_spans_with_llm(&app.state, SERVICE, 50).await.is_err());

        assert_eq!(distinct_service_names(&app.state).await.unwrap(), [SERVICE]);
    }

    #[tokio::test]
    async fn the_llm_filter_keeps_the_roots_of_indexed_traces_with_llm_spans() {
        let mut app = test_app();
        app.index_cold_file(
            "a.parquet",
            &[
                root("trace-llm-old", 1_000),
                llm_child("trace-llm-old", 1_010),
                root("trace-plain", 2_000),
                root("trace-llm-new", 3_000),
                llm_child("trace-llm-new", 3_010),
            ],
        );

        let roots = root_spans(&app.state, SERVICE, 50).await.unwrap();
        assert_eq!(
            span_ids(&roots),
            [
                "trace-llm-new-root",
                "trace-plain-root",
                "trace-llm-old-root"
            ]
        );

        let llm_roots = root_spans_with_llm(&app.state, SERVICE, 50).await.unwrap();
        assert_eq!(
            span_ids(&llm_roots),
            ["trace-llm-new-root", "trace-llm-old-root"]
        );

        let newest = root_spans_with_llm(&app.state, SERVICE, 1).await.unwrap();
        assert_eq!(span_ids(&newest), ["trace-llm-new-root"]);

        let other_service = root_spans_with_llm(&app.state, "billing", 50)
            .await
            .unwrap();
        assert!(other_service.is_empty());
    }

    #[tokio::test]
    async fn the_llm_filter_examines_five_recent_roots_per_requested_result() {
        let mut app = test_app();
        // One LLM trace, then five newer traces without LLM spans.
        let mut spans = vec![root("trace-llm", 1_000), llm_child("trace-llm", 1_010)];
        for index in 0..5 {
            spans.push(root(&format!("trace-plain-{index}"), 2_000 + index * 1_000));
        }
        app.index_cold_file("a.parquet", &spans);

        // One result examines the five newest roots. None is in an LLM trace.
        let one = root_spans_with_llm(&app.state, SERVICE, 1).await.unwrap();
        assert!(one.is_empty());

        // Two results examine ten roots, which reaches the LLM trace.
        let two = root_spans_with_llm(&app.state, SERVICE, 2).await.unwrap();
        assert_eq!(span_ids(&two), ["trace-llm-root"]);
    }

    #[tokio::test]
    async fn the_llm_filter_finds_llm_spans_that_are_still_in_the_hot_snapshot() {
        let mut app = test_app();
        // This root is flushed and indexed. Its LLM span is not flushed yet.
        app.index_cold_file("a.parquet", &[root("trace-split", 1_000)]);
        let hot_snapshot = app.write_hot_snapshot(&[
            llm_child("trace-split", 1_010),
            root("trace-hot", 2_000),
            llm_child("trace-hot", 2_010),
            root("trace-plain", 3_000),
        ]);
        app.state.ingestion = ingestion_reporting(Some(&hot_snapshot), &[]).await;

        let llm_roots = root_spans_with_llm(&app.state, SERVICE, 50).await.unwrap();

        assert_eq!(span_ids(&llm_roots), ["trace-hot-root", "trace-split-root"]);
    }

    #[tokio::test]
    async fn the_llm_filter_finds_llm_spans_in_a_flushed_file_that_is_not_indexed_yet() {
        let mut app = test_app();
        // One trace is indexed whole. Another has only its root indexed: its
        // LLM span is in the flushed file the indexer has not reached.
        app.index_cold_file(
            "a.parquet",
            &[
                root("trace-indexed", 1_000),
                llm_child("trace-indexed", 1_010),
                root("trace-split", 2_000),
            ],
        );
        let recent = app.write_cold_file(
            "recent.parquet",
            &[
                llm_child("trace-split", 2_010),
                root("trace-recent", 3_000),
                llm_child("trace-recent", 3_010),
                root("trace-recent-plain", 4_000),
            ],
        );
        let hot_snapshot =
            app.write_hot_snapshot(&[root("trace-hot", 5_000), llm_child("trace-hot", 5_010)]);
        app.state.ingestion = ingestion_reporting(Some(&hot_snapshot), &[recent]).await;

        let llm_roots = root_spans_with_llm(&app.state, SERVICE, 50).await.unwrap();
        assert_eq!(
            span_ids(&llm_roots),
            [
                "trace-hot-root",
                "trace-recent-root",
                "trace-split-root",
                "trace-indexed-root"
            ]
        );

        let newest = root_spans_with_llm(&app.state, SERVICE, 2).await.unwrap();
        assert_eq!(span_ids(&newest), ["trace-hot-root", "trace-recent-root"]);
    }

    /// The listing reads its root spans, ingestion flushes, and the listing
    /// then classifies them. The spans it needs are in a file that only
    /// ingestion's second answer names.
    #[tokio::test]
    async fn the_llm_filter_asks_ingestion_again_and_finds_a_file_flushed_between_its_reads() {
        let mut app = test_app();
        let hot_snapshot = app.write_hot_snapshot(&[root("trace-1", 1_000)]);
        let flushed = app.write_cold_file(
            "flushed.parquet",
            &[root("trace-1", 1_000), llm_child("trace-1", 1_010)],
        );
        let before_the_flush: (Option<&str>, &[String]) = (Some(&hot_snapshot), &[]);
        let after_the_flush: (Option<&str>, &[String]) = (None, std::slice::from_ref(&flushed));
        app.state.ingestion =
            ingestion_reporting_in_turn(&[before_the_flush, after_the_flush]).await;

        let llm_roots = root_spans_with_llm(&app.state, SERVICE, 50).await.unwrap();

        assert_eq!(span_ids(&llm_roots), ["trace-1-root"]);
    }

    /// Ingestion removes the snapshot between the listing's two reads and
    /// names it once more. The second read fails, and the whole listing runs
    /// again over what ingestion names then.
    #[tokio::test]
    async fn the_llm_filter_runs_again_when_the_snapshot_is_gone_at_its_second_read() {
        let mut app = test_app();
        let hot_snapshot =
            app.write_hot_snapshot(&[root("trace-1", 1_000), llm_child("trace-1", 1_010)]);
        let gone = app
            .parquet_directory
            .with_file_name("removed_snapshot.parquet");
        let gone = gone.to_str().unwrap();
        let there: (Option<&str>, &[String]) = (Some(&hot_snapshot), &[]);
        let removed: (Option<&str>, &[String]) = (Some(gone), &[]);

        // First attempt: root spans, then a snapshot that is gone. Second
        // attempt: both reads find the snapshot.
        app.state.ingestion = ingestion_reporting_in_turn(&[there, removed, there]).await;
        let llm_roots = root_spans_with_llm(&app.state, SERVICE, 50).await.unwrap();
        assert_eq!(span_ids(&llm_roots), ["trace-1-root"]);

        // Gone at the second read of both attempts: the listing fails.
        app.state.ingestion = ingestion_reporting_in_turn(&[there, removed, there, removed]).await;
        assert!(root_spans_with_llm(&app.state, SERVICE, 50).await.is_err());
    }

    #[tokio::test]
    async fn listings_read_the_newest_twenty_indexed_files_and_identity_queries_read_all() {
        let mut app = test_app();
        // Twenty-one indexed files, oldest first. Each holds one Workflow
        // span. The oldest also holds the only Agent span.
        for index in 0..21 {
            let start_time_ns = 1_000 * (index + 1);
            let mut spans = vec![
                TestSpan::new(
                    &format!("trace-{index}"),
                    &format!("workflow-{index}"),
                    SERVICE,
                )
                .times(start_time_ns, start_time_ns + 100)
                .attributes(&executable("workflow", &format!("run-{index}"))),
            ];
            if index == 0 {
                spans.push(
                    TestSpan::new("trace-0", "agent-0", SERVICE)
                        .times(start_time_ns, start_time_ns + 100)
                        .attributes(&executable("agent", "agent-run")),
                );
            }
            app.index_cold_file(&format!("{index:02}.parquet"), &spans);
        }

        let listed = service_spans(&app.state, SERVICE, LARGE_PAGE)
            .await
            .unwrap();
        assert_eq!(listed.len(), 20);
        assert_eq!(listed[0].span_id, "workflow-20");
        assert_eq!(listed[19].span_id, "workflow-1");

        let roots = root_spans(&app.state, SERVICE, LARGE_PAGE).await.unwrap();
        assert_eq!(roots.len(), 20);
        assert_eq!(roots[19].span_id, "workflow-1");

        let workflows = workflow_spans(&app.state, SERVICE, LARGE_PAGE)
            .await
            .unwrap();
        assert_eq!(workflows.len(), 20);
        assert_eq!(workflows[19].span_id, "workflow-1");

        let agents = agent_spans(&app.state, SERVICE).await.unwrap();
        assert_eq!(span_ids(&agents), ["agent-0"]);

        let oldest = executable_spans(&app.state, SERVICE, "workflow", "run-0")
            .await
            .unwrap();
        assert_eq!(span_ids(&oldest), ["workflow-0"]);
    }

    #[tokio::test]
    async fn flushed_files_that_are_not_indexed_yet_are_read_through_the_recent_cold_bridge() {
        let mut app = test_app();
        let recent = app.write_cold_file(
            "recent.parquet",
            &[
                TestSpan::new("trace-1", "workflow-1", SERVICE)
                    .attributes(&executable("workflow", "run-1")),
                TestSpan::new("trace-1", "agent-1", SERVICE)
                    .parent("workflow-1")
                    .attributes(&executable("agent", "agent-run-1")),
            ],
        );
        app.state.ingestion = ingestion_reporting(None, &[recent]).await;
        let state = &app.state;

        assert_eq!(distinct_service_names(state).await.unwrap(), [SERVICE]);
        assert_eq!(trace_spans(state, "trace-1").await.unwrap().len(), 2);
        let found = span(state, "trace-1", "agent-1").await.unwrap();
        assert_eq!(found.unwrap().span_id, "agent-1");
        let unknown = span(state, "trace-1", "missing").await.unwrap();
        assert!(unknown.is_none());

        let listed = service_spans(state, SERVICE, LARGE_PAGE).await.unwrap();
        assert_eq!(listed.len(), 2);
        let roots = root_spans(state, SERVICE, LARGE_PAGE).await.unwrap();
        assert_eq!(span_ids(&roots), ["workflow-1"]);
        let workflows = workflow_spans(state, SERVICE, LARGE_PAGE).await.unwrap();
        assert_eq!(span_ids(&workflows), ["workflow-1"]);
        let agents = agent_spans(state, SERVICE).await.unwrap();
        assert_eq!(span_ids(&agents), ["agent-1"]);
        let resolved = executable_spans(state, SERVICE, "workflow", "run-1")
            .await
            .unwrap();
        assert_eq!(span_ids(&resolved), ["workflow-1"]);
    }

    #[tokio::test]
    async fn the_recent_cold_bridge_is_bounded_for_listings_and_complete_for_identity_queries() {
        let mut app = test_app();
        // Twenty-one unindexed files, in the order ingestion reports them.
        // Each holds one Agent span of the shared service and one span of a
        // service that exists only in that file.
        let mut recent = Vec::new();
        for index in 0..21 {
            recent.push(
                app.write_cold_file(
                    &format!("recent-{index:02}.parquet"),
                    &[
                        TestSpan::new(
                            &format!("trace-{index}"),
                            &format!("agent-{index}"),
                            SERVICE,
                        )
                        .attributes(&executable("agent", &format!("run-{index}"))),
                        TestSpan::new(
                            &format!("trace-{index}"),
                            &format!("other-{index}"),
                            &format!("only-in-file-{index:02}"),
                        ),
                    ],
                ),
            );
        }
        app.state.ingestion = ingestion_reporting(None, &recent).await;
        let state = &app.state;

        // Service discovery reads the first five.
        assert_eq!(
            distinct_service_names(state).await.unwrap(),
            [
                SERVICE,
                "only-in-file-00",
                "only-in-file-01",
                "only-in-file-02",
                "only-in-file-03",
                "only-in-file-04",
            ]
        );

        // Trace and service listings read the first twenty.
        assert_eq!(trace_spans(state, "trace-19").await.unwrap().len(), 2);
        assert!(trace_spans(state, "trace-20").await.unwrap().is_empty());
        let beyond = span(state, "trace-20", "agent-20").await.unwrap();
        assert!(beyond.is_none());
        let listed = service_spans(state, SERVICE, LARGE_PAGE).await.unwrap();
        assert_eq!(listed.len(), 20);

        // Agent and identity queries read every one.
        assert_eq!(agent_spans(state, SERVICE).await.unwrap().len(), 21);
        let last = executable_spans(state, SERVICE, "agent", "run-20")
            .await
            .unwrap();
        assert_eq!(span_ids(&last), ["agent-20"]);
    }

    #[tokio::test]
    async fn unflushed_spans_are_read_from_the_hot_snapshot_and_cold_wins_for_a_flushed_span() {
        let mut app = test_app();
        app.index_cold_file(
            "a.parquet",
            &[TestSpan::new("trace-1", "span-1", SERVICE).name("from-cold")],
        );
        let hot_snapshot = app.write_hot_snapshot(&[
            TestSpan::new("trace-1", "span-1", SERVICE).name("from-hot"),
            TestSpan::new("trace-1", "workflow-1", SERVICE)
                .name("hot-workflow")
                .parent("span-1")
                .attributes(&executable("workflow", "run-1")),
            TestSpan::new("trace-1", "agent-1", SERVICE)
                .name("hot-agent")
                .parent("workflow-1")
                .attributes(&executable("agent", "agent-run-1")),
            TestSpan::new("trace-2", "span-2", "billing").name("hot-service"),
        ]);
        app.state.ingestion = ingestion_reporting(Some(&hot_snapshot), &[]).await;
        let state = &app.state;

        assert_eq!(
            distinct_service_names(state).await.unwrap(),
            ["billing", SERVICE]
        );

        let mut trace = trace_spans(state, "trace-1").await.unwrap();
        trace.sort_by(|left, right| left.span_id.cmp(&right.span_id));
        let names: Vec<&str> = trace.iter().map(|span| span.name.as_str()).collect();
        assert_eq!(names, ["hot-agent", "from-cold", "hot-workflow"]);

        let flushed = span(state, "trace-1", "span-1").await.unwrap();
        assert_eq!(flushed.unwrap().name, "from-cold");
        let unflushed = span(state, "trace-1", "agent-1").await.unwrap();
        assert_eq!(unflushed.unwrap().name, "hot-agent");

        let listed = service_spans(state, SERVICE, LARGE_PAGE).await.unwrap();
        assert_eq!(listed.len(), 3);
        let roots = root_spans(state, SERVICE, LARGE_PAGE).await.unwrap();
        assert_eq!(roots.len(), 1);
        assert_eq!(roots[0].name, "from-cold");
        let workflows = workflow_spans(state, SERVICE, LARGE_PAGE).await.unwrap();
        assert_eq!(span_ids(&workflows), ["workflow-1"]);
        let agents = agent_spans(state, SERVICE).await.unwrap();
        assert_eq!(span_ids(&agents), ["agent-1"]);
        let resolved = executable_spans(state, SERVICE, "agent", "agent-run-1")
            .await
            .unwrap();
        assert_eq!(span_ids(&resolved), ["agent-1"]);
    }
}
