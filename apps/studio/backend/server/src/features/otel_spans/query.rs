//! DataFusion queries over the two span tiers.
//!
//! - COLD: Parquet files from WAL flushes, selected through the metadata index
//!   and bridged with ingestion's recent-cold list.
//! - HOT: the on-demand Parquet snapshot of unflushed spans.
//!
//! Both tiers are queried together and deduplicated by `(trace_id, span_id)`
//! with COLD taking precedence. One process-wide runtime owns the memory pool,
//! the disk manager, and the caches, so the spill pool bounds all concurrent
//! queries together.
//!
//! Ingestion replaces the hot snapshot file while queries read it. A query
//! that cannot read the snapshot it was given fails here, and the repository
//! asks ingestion again (ingestion ADR-002).

use std::collections::HashSet;
use std::path::Path;
use std::sync::Arc;

use datafusion::arrow::array::{
    Array, ArrayRef, AsArray, Int64Array, LargeStringArray, RecordBatch, StringArray,
    StringViewArray,
};
use datafusion::arrow::compute::cast;
use datafusion::arrow::datatypes::{DataType, TimeUnit};
use datafusion::common::ScalarValue;
use datafusion::error::{DataFusionError, Result};
use datafusion::execution::disk_manager::{DiskManagerBuilder, DiskManagerMode};
use datafusion::execution::memory_pool::FairSpillPool;
use datafusion::execution::runtime_env::{RuntimeEnv, RuntimeEnvBuilder};
use datafusion::prelude::{ParquetReadOptions, SessionConfig, SessionContext, col, lit};
use junjo_evidence::json::{Json, JsonObject};
use junjo_evidence::trace_evidence::schemas::NormalizedSpanEvidence;
use serde::Serialize;
use serde_json::value::RawValue;

use crate::config::DataFusionConfig;
use crate::features::parquet_indexer::classify::classify_attributes;
use crate::timestamps::format_span_timestamp;

const COLD_TABLE: &str = "cold_spans";
const HOT_TABLE: &str = "hot_spans";

/// A root span has no parent. Ingestion stores a missing parent as null.
const ROOT_SPAN_FILTER: &str = "(parent_span_id IS NULL OR parent_span_id = '')";

/// Substring prefilters over the stored attributes text.
///
/// Ingestion writes attributes as compact JSON, so a member's text is stable.
/// Filtering in SQL means a row limit counts spans of the wanted kind rather
/// than arbitrary spans. A substring cannot decide the question by itself: the
/// same text can sit inside a nested value. Every prefilter is therefore
/// followed by an exact check of the parsed attributes.
const WORKFLOW_SPAN_PREFILTER: &str = r#"attributes LIKE '%"junjo.span_type":"workflow"%'"#;
const AGENT_SPAN_PREFILTER: &str = r#"attributes LIKE '%"junjo.span_type":"agent"%'"#;

/// Narrows the scan to spans that carry both identity attributes and contain
/// the wanted runtime identity as JSON text. The identity is the bound value
/// `$2` and not part of a pattern: `LIKE` would read `%` and `_` inside it as
/// wildcards. Without it the query would return every executable span of the
/// files it reads to keep one.
const EXECUTABLE_SPAN_PREFILTER: &str = r#"attributes LIKE '%"junjo.span_type"%'
    AND attributes LIKE '%"junjo.executable_runtime_id"%'
    AND contains(attributes, $2)"#;

/// The columns the raw span API returns, in the stored span schema's names.
const SPAN_COLUMNS: &str = "
    span_id,
    trace_id,
    parent_span_id,
    service_name,
    name,
    span_kind,
    CAST(start_time AS BIGINT) AS start_time_ns,
    CAST(end_time AS BIGINT) AS end_time_ns,
    status_code,
    status_message,
    attributes,
    events,
    links,
    trace_flags,
    trace_state,
    dropped_attributes_count,
    dropped_events_count,
    dropped_links_count,
    resource_attributes,
    resource_dropped_attributes_count";

/// The same columns after the tiers are combined.
const COMBINED_SPAN_COLUMNS: &str = "
    span_id,
    trace_id,
    parent_span_id,
    service_name,
    name,
    span_kind,
    start_time_ns,
    end_time_ns,
    status_code,
    status_message,
    attributes,
    events,
    links,
    trace_flags,
    trace_state,
    dropped_attributes_count,
    dropped_events_count,
    dropped_links_count,
    resource_attributes,
    resource_dropped_attributes_count";

/// The files one query reads.
#[derive(Debug, Clone, Default)]
pub struct QuerySources {
    pub cold_files: Vec<String>,
    pub hot_snapshot: Option<String>,
}

/// A place in a walk over spans, newest first.
#[derive(Debug, Clone)]
pub struct SpanPlace {
    pub start_time_ns: i64,
    /// The trace and span identifiers of the span at this place. Without
    /// them the place is before every span that starts at this time.
    pub span: Option<(String, String)>,
}

/// What every span of a walk over Agent spans satisfies inside the query, so
/// a page holds spans the caller can use.
#[derive(Debug, Clone, Default)]
pub struct AgentSpanBounds {
    /// Only spans that started at or after this time.
    pub started_from_ns: Option<i64>,
    /// Only spans that ended at or before this time.
    pub ended_by_ns: Option<i64>,
    /// Text the stored attributes contain. Like the span-type prefilters,
    /// a substring cannot decide the question: the caller makes the exact
    /// check.
    pub attributes_contain: Vec<String>,
    /// Text the stored resource attributes contain.
    pub resource_attributes_contain: Vec<String>,
}

/// One page of a walk over the Agent spans of one service.
#[derive(Debug)]
pub struct AgentSpanPage {
    /// The indexed cold files that can hold the page's spans.
    pub indexed_files: Vec<String>,
    pub bounds: AgentSpanBounds,
    /// Only spans after this place.
    pub after: Option<SpanPlace>,
    /// Only spans that started after this time. Older spans can be in
    /// indexed files that are not among the page's.
    pub started_after_ns: Option<i64>,
    pub limit: usize,
}

/// One span in the raw observability API's shape.
///
/// The four stored JSON columns are validated and passed through as raw JSON.
/// They are not parsed into values and re-serialized.
#[derive(Debug, Serialize)]
pub struct Span {
    pub trace_id: String,
    pub span_id: String,
    pub parent_span_id: Option<String>,
    pub service_name: String,
    pub name: String,
    pub kind: &'static str,
    pub start_time: String,
    /// The start time as stored, in nanoseconds since the Unix epoch. It is
    /// not part of the API's span, which carries `start_time`.
    #[serde(skip)]
    pub start_time_ns: Option<i64>,
    pub end_time: String,
    pub status_code: String,
    pub status_message: String,
    pub attributes_json: Box<RawValue>,
    pub events_json: Box<RawValue>,
    pub links_json: Box<RawValue>,
    pub trace_flags: i64,
    pub trace_state: Option<String>,
    pub dropped_attributes_count: i64,
    pub dropped_events_count: i64,
    pub dropped_links_count: i64,
    pub resource_attributes_json: Box<RawValue>,
    pub resource_dropped_attributes_count: i64,
}

impl Span {
    /// The span with its four JSON columns parsed, as evidence logic reads it.
    ///
    /// The raw span API passes any valid JSON through. Evidence logic needs
    /// attributes that are objects and events and links that are arrays, so a
    /// column of any other kind reads as empty, as invalid JSON already does.
    pub fn to_evidence(&self) -> NormalizedSpanEvidence {
        NormalizedSpanEvidence {
            trace_id: self.trace_id.clone(),
            span_id: self.span_id.clone(),
            parent_span_id: self.parent_span_id.clone(),
            service_name: self.service_name.clone(),
            name: self.name.clone(),
            kind: self.kind.to_string(),
            start_time: self.start_time.clone(),
            end_time: self.end_time.clone(),
            status_code: self.status_code.clone(),
            status_message: self.status_message.clone(),
            attributes_json: json_object(&self.attributes_json),
            events_json: json_array(&self.events_json),
            links_json: json_array(&self.links_json),
            trace_flags: self.trace_flags,
            trace_state: self.trace_state.clone(),
            dropped_attributes_count: self.dropped_attributes_count,
            dropped_events_count: self.dropped_events_count,
            dropped_links_count: self.dropped_links_count,
            resource_attributes_json: json_object(&self.resource_attributes_json),
            resource_dropped_attributes_count: self.resource_dropped_attributes_count,
        }
    }

    /// Whether the span's attributes name exactly this executable.
    ///
    /// This is the exact check behind `EXECUTABLE_SPAN_PREFILTER`: both values
    /// are compared as parsed text.
    fn is_executable(&self, executable_type: &str, runtime_id: &str) -> bool {
        let attributes = json_object(&self.attributes_json);
        attributes.get("junjo.span_type").and_then(Json::as_str) == Some(executable_type)
            && attributes
                .get("junjo.executable_runtime_id")
                .and_then(Json::as_str)
                == Some(runtime_id)
    }
}

/// A stored JSON column as an object. Anything else reads as empty.
fn json_object(column: &RawValue) -> JsonObject {
    match serde_json::from_str(column.get()) {
        Ok(Json::Object(object)) => object,
        _ => JsonObject::new(),
    }
}

/// A stored JSON column as an array. Anything else reads as empty.
fn json_array(column: &RawValue) -> Vec<Json> {
    match serde_json::from_str(column.get()) {
        Ok(Json::Array(items)) => items,
        _ => Vec::new(),
    }
}

pub struct QueryEngine {
    runtime: Arc<RuntimeEnv>,
    session_config: SessionConfig,
}

impl QueryEngine {
    /// Build the process-wide DataFusion runtime from the `JUNJO_DF_*`
    /// settings.
    pub fn new(config: &DataFusionConfig) -> anyhow::Result<Self> {
        // Filters are applied while Parquet is decoded: the filter's columns
        // are decoded first, and the other columns only for the rows that
        // match. Reordering runs the cheaper filters first. Studio ADR-011
        // records the measurement behind both.
        let session_config = SessionConfig::new()
            .with_target_partitions(config.target_partitions)
            .with_batch_size(config.batch_size)
            .with_parquet_pruning(config.parquet_pruning)
            .set_bool("datafusion.execution.parquet.pushdown_filters", true)
            .set_bool("datafusion.execution.parquet.reorder_filters", true);

        let mut runtime = RuntimeEnvBuilder::new();
        if config.spill_enabled {
            std::fs::create_dir_all(&config.spill_path)?;
            runtime = runtime
                .with_temp_file_path(&config.spill_path)
                .with_memory_pool(Arc::new(FairSpillPool::new(config.spill_pool_bytes)));
        } else {
            runtime = runtime.with_disk_manager_builder(
                DiskManagerBuilder::default().with_mode(DiskManagerMode::Disabled),
            );
        }

        Ok(Self {
            runtime: runtime.build_arc()?,
            session_config,
        })
    }

    /// A lightweight per-request session on the shared runtime.
    fn context(&self) -> SessionContext {
        SessionContext::new_with_config_rt(self.session_config.clone(), self.runtime.clone())
    }

    /// Register both tiers. Returns which tiers have data to read.
    async fn register(&self, context: &SessionContext, files: &TierFiles) -> Result<Tiers> {
        Ok(Tiers {
            cold: register_parquet(context, COLD_TABLE, &files.cold).await?,
            hot: register_parquet(context, HOT_TABLE, &files.hot).await?,
        })
    }

    /// The files without the cold files whose footers cannot be read.
    ///
    /// Registering a table reads only its first file's footer, so a damaged
    /// cold file fails a query either at registration or while it runs. A
    /// failed query is therefore run once more over these files, and a query
    /// with no damaged file never pays for the check.
    ///
    /// The hot snapshot is not checked. A query that fails while reading it
    /// has met a newer snapshot, and running it again without the hot tier
    /// would answer without the newest spans. It fails, and the repository
    /// asks ingestion again.
    async fn readable(&self, files: &TierFiles) -> TierFiles {
        let context = self.context();
        TierFiles {
            cold: readable_files(&context, COLD_TABLE, &files.cold).await,
            hot: files.hot.clone(),
        }
    }

    /// Distinct service names in the given sources, alphabetically.
    pub async fn distinct_service_names(&self, sources: &QuerySources) -> Result<Vec<String>> {
        let files = TierFiles::usable(sources)?;
        match self.service_names(&files).await {
            Err(error) => {
                let readable = self.readable(&files).await;
                if readable == files {
                    return Err(error);
                }
                self.service_names(&readable).await
            }
            names => names,
        }
    }

    async fn service_names(&self, files: &TierFiles) -> Result<Vec<String>> {
        let context = self.context();
        let tiers = self.register(&context, files).await?;
        let mut selects = Vec::new();
        if tiers.cold {
            selects.push(format!("SELECT DISTINCT service_name FROM {COLD_TABLE}"));
        }
        if tiers.hot {
            selects.push(format!("SELECT DISTINCT service_name FROM {HOT_TABLE}"));
        }
        if selects.is_empty() {
            return Ok(Vec::new());
        }
        // UNION removes duplicates across tiers.
        let sql = format!(
            "SELECT service_name FROM ({}) ORDER BY service_name",
            selects.join(" UNION ")
        );
        collect_service_names(&context, &sql).await
    }

    /// Run one span query over the given sources.
    pub async fn run(&self, sources: &QuerySources, query: SpanQuery<'_>) -> Result<Vec<Span>> {
        match query {
            SpanQuery::Trace { trace_id } => self.trace_spans(sources, trace_id).await,
            SpanQuery::Span { trace_id, span_id } => {
                let span = self.span(sources, trace_id, span_id).await?;
                Ok(span.into_iter().collect())
            }
            SpanQuery::Service {
                service_name,
                api_key_id,
                limit,
            } => {
                self.service_spans(sources, service_name, limit, api_key_id)
                    .await
            }
            SpanQuery::Roots {
                service_name,
                api_key_id,
                limit,
            } => {
                self.root_spans(sources, service_name, limit, api_key_id)
                    .await
            }
            SpanQuery::Workflows {
                service_name,
                api_key_id,
                limit,
            } => {
                self.workflow_spans(sources, service_name, limit, api_key_id)
                    .await
            }
            SpanQuery::Agents { service_name, page } => {
                self.agent_spans(sources, service_name, page).await
            }
            SpanQuery::Executable {
                service_name,
                executable_type,
                runtime_id,
            } => {
                self.executable_spans(sources, service_name, executable_type, runtime_id)
                    .await
            }
        }
    }

    /// Run one span query over both tiers, newest first.
    ///
    /// `filter` is a SQL predicate over the stored span columns. Its values are
    /// the bound `parameters`: caller-supplied text is never part of the SQL.
    /// A limit applies after the tiers are merged and ordered.
    async fn query_spans(
        &self,
        sources: &QuerySources,
        filter: &str,
        parameters: Vec<ScalarValue>,
        limit: Option<usize>,
    ) -> Result<Vec<Span>> {
        self.ordered_spans(sources, filter, parameters, limit, Order::NewestFirst)
            .await
    }

    /// Run one span query over both tiers in the given order.
    async fn ordered_spans(
        &self,
        sources: &QuerySources,
        filter: &str,
        parameters: Vec<ScalarValue>,
        limit: Option<usize>,
        order: Order,
    ) -> Result<Vec<Span>> {
        let files = TierFiles::usable(sources)?;
        let batches = match self
            .span_batches(&files, filter, &parameters, limit, order)
            .await
        {
            Ok(batches) => batches,
            Err(error) => {
                let readable = self.readable(&files).await;
                if readable == files {
                    return Err(error);
                }
                self.span_batches(&readable, filter, &parameters, limit, order)
                    .await?
            }
        };
        let mut spans = Vec::new();
        for batch in &batches {
            append_spans(batch, &mut spans)?;
        }
        Ok(spans)
    }

    async fn span_batches(
        &self,
        files: &TierFiles,
        filter: &str,
        parameters: &[ScalarValue],
        limit: Option<usize>,
        order: Order,
    ) -> Result<Vec<RecordBatch>> {
        let context = self.context();
        let tiers = self.register(&context, files).await?;
        let Some(sql) = two_tier_sql(tiers, filter, limit, order) else {
            return Ok(Vec::new());
        };
        let mut frame = context
            .sql(&sql)
            .await?
            .with_param_values(parameters.to_vec())?;
        if let Some(limit) = limit {
            frame = frame.limit(0, Some(limit))?;
        }
        frame.collect().await
    }

    /// Every span of one trace, newest first.
    async fn trace_spans(&self, sources: &QuerySources, trace_id: &str) -> Result<Vec<Span>> {
        self.query_spans(
            sources,
            "trace_id = $1",
            vec![ScalarValue::from(trace_id)],
            None,
        )
        .await
    }

    /// One span of one trace.
    ///
    /// The span identifier is part of the query, so the engine drops the rest
    /// of the trace instead of returning it to be searched here.
    async fn span(
        &self,
        sources: &QuerySources,
        trace_id: &str,
        span_id: &str,
    ) -> Result<Option<Span>> {
        let spans = self
            .query_spans(
                sources,
                "trace_id = $1 AND span_id = $2",
                vec![ScalarValue::from(trace_id), ScalarValue::from(span_id)],
                Some(1),
            )
            .await?;
        Ok(spans.into_iter().next())
    }

    /// The newest spans of one service that pass `kind`, a filter over the
    /// stored span columns. With an API key identifier, only the spans that
    /// key sent.
    async fn listing(
        &self,
        sources: &QuerySources,
        kind: Option<&str>,
        service_name: &str,
        limit: usize,
        api_key_id: Option<&str>,
    ) -> Result<Vec<Span>> {
        let mut filter = String::from("service_name = $1");
        let mut parameters = vec![ScalarValue::from(service_name)];
        if let Some(kind) = kind {
            filter.push_str(" AND ");
            filter.push_str(kind);
        }
        if let Some(api_key_id) = api_key_id {
            filter.push_str(" AND api_key_id = $2");
            parameters.push(ScalarValue::from(api_key_id));
        }
        self.query_spans(sources, &filter, parameters, Some(limit))
            .await
    }

    /// The newest spans of one service.
    async fn service_spans(
        &self,
        sources: &QuerySources,
        service_name: &str,
        limit: usize,
        api_key_id: Option<&str>,
    ) -> Result<Vec<Span>> {
        self.listing(sources, None, service_name, limit, api_key_id)
            .await
    }

    /// The newest root spans of one service.
    async fn root_spans(
        &self,
        sources: &QuerySources,
        service_name: &str,
        limit: usize,
        api_key_id: Option<&str>,
    ) -> Result<Vec<Span>> {
        let kind = Some(ROOT_SPAN_FILTER);
        self.listing(sources, kind, service_name, limit, api_key_id)
            .await
    }

    /// The newest Workflow spans of one service.
    ///
    /// The limit counts spans that pass the substring prefilter. The exact
    /// check runs on those rows, so it can only remove spans from the page.
    async fn workflow_spans(
        &self,
        sources: &QuerySources,
        service_name: &str,
        limit: usize,
        api_key_id: Option<&str>,
    ) -> Result<Vec<Span>> {
        let kind = Some(WORKFLOW_SPAN_PREFILTER);
        let mut spans = self
            .listing(sources, kind, service_name, limit, api_key_id)
            .await?;
        spans.retain(|span| classify_attributes(span.attributes_json.get()).is_workflow);
        Ok(spans)
    }

    /// One page of the spans of one service that pass the Agent prefilter,
    /// in walk order.
    ///
    /// The exact check is the caller's. The walk continues after the page's
    /// last span, whether or not that span is an Agent span.
    ///
    /// Times are compared as the stored column's own type, so the Parquet
    /// reader can leave out row groups by their statistics.
    async fn agent_spans(
        &self,
        sources: &QuerySources,
        service_name: &str,
        page: &AgentSpanPage,
    ) -> Result<Vec<Span>> {
        let mut filter = String::from("service_name = $1");
        let mut parameters = vec![ScalarValue::from(service_name)];
        let mut time = |nanoseconds: i64| {
            parameters.push(ScalarValue::from(nanoseconds));
            format!("to_timestamp_nanos(${})", parameters.len())
        };
        if let Some(started_from_ns) = page.bounds.started_from_ns {
            filter.push_str(&format!(" AND start_time >= {}", time(started_from_ns)));
        }
        if let Some(ended_by_ns) = page.bounds.ended_by_ns {
            filter.push_str(&format!(" AND end_time <= {}", time(ended_by_ns)));
        }
        if let Some(started_after_ns) = page.started_after_ns {
            filter.push_str(&format!(" AND start_time > {}", time(started_after_ns)));
        }
        if let Some(place) = &page.after {
            let started = time(place.start_time_ns);
            filter.push_str(&format!(" AND start_time <= {started}"));
            if let Some((trace_id, span_id)) = &place.span {
                parameters.push(ScalarValue::from(trace_id.as_str()));
                parameters.push(ScalarValue::from(span_id.as_str()));
                let (trace, span) = (parameters.len() - 1, parameters.len());
                filter.push_str(&format!(
                    " AND (start_time < {started}
                        OR trace_id > ${trace}
                        OR (trace_id = ${trace} AND span_id > ${span}))"
                ));
            }
        }
        filter.push_str(" AND ");
        filter.push_str(AGENT_SPAN_PREFILTER);
        // The text is a bound value, so `LIKE` wildcards in it mean nothing.
        let contained = [
            ("attributes", &page.bounds.attributes_contain),
            (
                "resource_attributes",
                &page.bounds.resource_attributes_contain,
            ),
        ];
        for (column, texts) in contained {
            for text in texts {
                parameters.push(ScalarValue::from(text.as_str()));
                filter.push_str(&format!(" AND contains({column}, ${})", parameters.len()));
            }
        }
        self.ordered_spans(sources, &filter, parameters, Some(page.limit), Order::Walk)
            .await
    }

    /// Every span of one service that is the executable with exactly this type
    /// and runtime identity, newest first.
    async fn executable_spans(
        &self,
        sources: &QuerySources,
        service_name: &str,
        executable_type: &str,
        runtime_id: &str,
    ) -> Result<Vec<Span>> {
        // The identity as ingestion writes a JSON string.
        let stored_runtime_id = Json::from(runtime_id).to_string();
        let mut spans = self
            .query_spans(
                sources,
                &format!("service_name = $1 AND {EXECUTABLE_SPAN_PREFILTER}"),
                vec![
                    ScalarValue::from(service_name),
                    ScalarValue::from(stored_runtime_id),
                ],
                None,
            )
            .await?;
        spans.retain(|span| span.is_executable(executable_type, runtime_id));
        Ok(spans)
    }

    /// The candidate traces that have an LLM span of one service among the
    /// spans the metadata index does not cover.
    ///
    /// `unindexed` names the hot snapshot and the flushed files the indexer
    /// has not reached. The index knows LLM traces only once their file is
    /// indexed, so these spans are classified here with the indexer's own
    /// rule.
    ///
    /// Only the candidates' spans are decoded: the service, the trace
    /// identifiers, and the start time are filters the Parquet reader applies
    /// before it decodes attributes. `since_ns` is the start time of the
    /// oldest candidate root span. A span of a trace does not start before
    /// the trace's root span, so older spans are left out: whole row groups
    /// by their statistics, and rows by a comparison of integers.
    pub async fn unindexed_llm_trace_ids(
        &self,
        unindexed: &QuerySources,
        service_name: &str,
        candidate_trace_ids: &HashSet<String>,
        since_ns: Option<i64>,
    ) -> Result<HashSet<String>> {
        let files = TierFiles::usable(unindexed)?;
        match self
            .llm_trace_ids(&files, service_name, candidate_trace_ids, since_ns)
            .await
        {
            Err(error) => {
                let readable = self.readable(&files).await;
                if readable == files {
                    return Err(error);
                }
                self.llm_trace_ids(&readable, service_name, candidate_trace_ids, since_ns)
                    .await
            }
            llm_trace_ids => llm_trace_ids,
        }
    }

    async fn llm_trace_ids(
        &self,
        files: &TierFiles,
        service_name: &str,
        candidate_trace_ids: &HashSet<String>,
        since_ns: Option<i64>,
    ) -> Result<HashSet<String>> {
        let context = self.context();
        let tiers = self.register(&context, files).await?;
        let candidates = candidate_trace_ids
            .iter()
            .map(|trace_id| lit(trace_id.as_str()))
            .collect();
        let wanted = col("service_name")
            .eq(lit(service_name))
            .and(col("trace_id").in_list(candidates, false));
        let mut llm_trace_ids = HashSet::new();
        for (present, table) in [(tiers.cold, COLD_TABLE), (tiers.hot, HOT_TABLE)] {
            if !present {
                continue;
            }
            let frame = context.table(table).await?;
            let mut wanted = wanted.clone();
            if let Some(since_ns) = since_ns {
                // The value has the stored column's own type, so the
                // comparison needs no cast and statistics can prune with it.
                let start_time = frame
                    .schema()
                    .field_with_unqualified_name("start_time")?
                    .data_type()
                    .clone();
                let DataType::Timestamp(TimeUnit::Nanosecond, timezone) = start_time else {
                    return Err(DataFusionError::Execution(format!(
                        "column start_time has unsupported type {start_time}"
                    )));
                };
                let since = ScalarValue::TimestampNanosecond(Some(since_ns), timezone);
                wanted = col("start_time").gt_eq(lit(since)).and(wanted);
            }
            let batches = frame
                .filter(wanted)?
                .select_columns(&["trace_id", "attributes"])?
                .collect()
                .await?;
            for batch in &batches {
                let trace_id_column = Text::column(batch, "trace_id")?;
                let attributes_column = Text::column(batch, "attributes")?;
                for row in 0..batch.num_rows() {
                    let (Some(trace_id), Some(attributes)) =
                        (trace_id_column.value(row), attributes_column.value(row))
                    else {
                        continue;
                    };
                    if !llm_trace_ids.contains(trace_id) && classify_attributes(attributes).is_llm {
                        llm_trace_ids.insert(trace_id.to_string());
                    }
                }
            }
        }
        Ok(llm_trace_ids)
    }
}

/// One span query, newest first.
///
/// The repository names the query it wants, so it can run the same query
/// again over the files ingestion names next.
#[derive(Debug, Clone, Copy)]
pub enum SpanQuery<'a> {
    /// Every span of one trace.
    Trace { trace_id: &'a str },
    /// One span of one trace.
    Span { trace_id: &'a str, span_id: &'a str },
    /// The newest spans of one service. With an API key identifier, here and
    /// in the two listings below, only the spans that key sent.
    Service {
        service_name: &'a str,
        api_key_id: Option<&'a str>,
        limit: usize,
    },
    /// The newest root spans of one service.
    Roots {
        service_name: &'a str,
        api_key_id: Option<&'a str>,
        limit: usize,
    },
    /// The newest Workflow spans of one service.
    Workflows {
        service_name: &'a str,
        api_key_id: Option<&'a str>,
        limit: usize,
    },
    /// One page of a walk over the Agent spans of one service.
    Agents {
        service_name: &'a str,
        page: &'a AgentSpanPage,
    },
    /// Every span of one service that is the executable with exactly this
    /// type and runtime identity.
    Executable {
        service_name: &'a str,
        executable_type: &'a str,
        runtime_id: &'a str,
    },
}

/// The order of a query's spans.
#[derive(Debug, Clone, Copy)]
enum Order {
    /// By start time, newest first. Spans that start together are in no
    /// particular order.
    NewestFirst,
    /// Newest first, and by trace and span identifier among spans that
    /// start together. A span's place is exact, so a walk can continue
    /// after it.
    Walk,
}

#[derive(Debug, Clone, Copy)]
struct Tiers {
    cold: bool,
    hot: bool,
}

/// The Parquet files one query reads, by tier.
#[derive(Debug, PartialEq)]
struct TierFiles {
    cold: Vec<String>,
    hot: Vec<String>,
}

impl TierFiles {
    /// The existing, non-empty cold files of the given sources, and the hot
    /// snapshot.
    fn usable(sources: &QuerySources) -> Result<Self> {
        Ok(Self {
            cold: usable_parquet_files(&sources.cold_files, COLD_TABLE),
            hot: match &sources.hot_snapshot {
                Some(hot_snapshot) => hot_snapshot_file(hot_snapshot)?,
                None => Vec::new(),
            },
        })
    }
}

/// The hot snapshot ingestion named, as the one file of the hot table.
///
/// Ingestion names a snapshot only when it holds spans, and it replaces and
/// removes the file in one step. A named snapshot that is not there was
/// removed after ingestion answered: its spans were flushed to a cold file
/// this query was not given. That is an error and not an empty tier, which
/// would answer without the newest spans.
fn hot_snapshot_file(hot_snapshot: &str) -> Result<Vec<String>> {
    match std::fs::metadata(hot_snapshot) {
        Ok(metadata) if metadata.is_file() => Ok(vec![hot_snapshot.to_string()]),
        Ok(_) => Err(DataFusionError::Execution(format!(
            "the hot snapshot {hot_snapshot} is not a file"
        ))),
        Err(error) => Err(DataFusionError::Execution(format!(
            "the hot snapshot {hot_snapshot} cannot be read: {error}"
        ))),
    }
}

/// Build the query that merges the available tiers. `filter` is a SQL
/// predicate over the stored span columns whose values are bound parameters.
///
/// A span is in both tiers only for a moment after a flush, and the cold copy
/// wins. A query with a `limit` wants its newest spans only. The newest
/// `limit` spans of the two tiers together are among the newest `limit` of
/// each tier, so duplicates are removed among those candidates and not among
/// every matching span of every file (ingestion ADR-002).
///
/// A walk reads a page that is shorter than it asked for as the end of the
/// files it read. Its hot copy of a span is still replaced by the cold one,
/// and a span stored twice in one tier keeps both copies, as it does when
/// there is one tier. Removing one would shorten the page.
fn two_tier_sql(tiers: Tiers, filter: &str, limit: Option<usize>, order: Order) -> Option<String> {
    let (order, numbering) = match order {
        Order::NewestFirst => ("ORDER BY start_time_ns DESC", "ROW_NUMBER()"),
        Order::Walk => ("ORDER BY start_time_ns DESC, trace_id, span_id", "RANK()"),
    };
    // Each tier's part of the union: every matching span, or its newest.
    let newest = match limit {
        Some(limit) => format!("{order} LIMIT {limit}"),
        None => String::new(),
    };
    match (tiers.cold, tiers.hot) {
        (false, false) => None,
        // One tier needs no deduplication.
        (true, false) => Some(format!(
            "SELECT {SPAN_COLUMNS} FROM {COLD_TABLE} WHERE {filter} {order}"
        )),
        (false, true) => Some(format!(
            "SELECT {SPAN_COLUMNS} FROM {HOT_TABLE} WHERE {filter} {order}"
        )),
        (true, true) => Some(format!(
            "WITH combined AS (
                 (SELECT {SPAN_COLUMNS}, 'cold' AS _tier FROM {COLD_TABLE}
                  WHERE {filter} {newest})
                 UNION ALL
                 (SELECT {SPAN_COLUMNS}, 'hot' AS _tier FROM {HOT_TABLE}
                  WHERE {filter} {newest})
             ),
             ranked AS (
                 SELECT *,
                     {numbering} OVER (
                         PARTITION BY trace_id, span_id
                         ORDER BY CASE _tier WHEN 'cold' THEN 0 ELSE 1 END
                     ) AS _rn
                 FROM combined
             )
             SELECT {COMBINED_SPAN_COLUMNS} FROM ranked WHERE _rn = 1 {order}"
        )),
    }
}

/// Keep existing, non-empty `.parquet` files, without duplicates.
fn usable_parquet_files(file_paths: &[String], table: &str) -> Vec<String> {
    let mut seen = HashSet::new();
    let mut usable = Vec::new();
    for file_path in file_paths {
        if file_path.is_empty() || !seen.insert(file_path.as_str()) {
            continue;
        }
        let path = Path::new(file_path);
        if path.extension().and_then(|extension| extension.to_str()) != Some("parquet") {
            tracing::warn!(
                table,
                file_path,
                "skipping non-parquet path during registration"
            );
            continue;
        }
        match std::fs::metadata(path) {
            Ok(metadata) if metadata.is_file() && metadata.len() > 0 => {
                usable.push(file_path.clone());
            }
            Ok(_) => {
                tracing::warn!(table, file_path, "skipping empty or non-file parquet path");
            }
            Err(error) => {
                tracing::warn!(table, file_path, %error, "skipping missing or unreadable parquet path");
            }
        }
    }
    usable
}

/// Register a set of Parquet files as one table. Returns whether the table
/// exists: no files is no table.
async fn register_parquet(context: &SessionContext, table: &str, files: &[String]) -> Result<bool> {
    if files.is_empty() {
        return Ok(false);
    }
    let frame = context
        .read_parquet(files.to_vec(), ParquetReadOptions::default())
        .await?;
    context.register_table(table, frame.into_view())?;
    Ok(true)
}

/// The files whose footers can be read, each checked by itself.
async fn readable_files(context: &SessionContext, table: &str, files: &[String]) -> Vec<String> {
    let mut readable = Vec::new();
    for file in files {
        match context
            .read_parquet(file.clone(), ParquetReadOptions::default())
            .await
        {
            Ok(_) => readable.push(file.clone()),
            Err(error) => {
                tracing::warn!(table, file_path = %file, %error, "skipping unreadable parquet file");
            }
        }
    }
    readable
}

async fn collect_service_names(context: &SessionContext, sql: &str) -> Result<Vec<String>> {
    let batches = context.sql(sql).await?.collect().await?;
    let mut names = Vec::new();
    for batch in &batches {
        let column = Text::column(batch, "service_name")?;
        for row in 0..batch.num_rows() {
            if let Some(name) = column.value(row) {
                names.push(name.to_string());
            }
        }
    }
    Ok(names)
}

/// A text column in whichever string encoding DataFusion produced.
enum Text<'a> {
    Utf8(&'a StringArray),
    LargeUtf8(&'a LargeStringArray),
    View(&'a StringViewArray),
}

impl<'a> Text<'a> {
    fn column(batch: &'a RecordBatch, name: &str) -> Result<Self> {
        let array = column(batch, name)?;
        match array.data_type() {
            DataType::Utf8 => Ok(Self::Utf8(array.as_string::<i32>())),
            DataType::LargeUtf8 => Ok(Self::LargeUtf8(array.as_string::<i64>())),
            DataType::Utf8View => Ok(Self::View(array.as_string_view())),
            other => Err(DataFusionError::Execution(format!(
                "column {name} has unsupported type {other}"
            ))),
        }
    }

    fn value(&self, row: usize) -> Option<&'a str> {
        match self {
            Self::Utf8(array) => (!array.is_null(row)).then(|| array.value(row)),
            Self::LargeUtf8(array) => (!array.is_null(row)).then(|| array.value(row)),
            Self::View(array) => (!array.is_null(row)).then(|| array.value(row)),
        }
    }
}

fn column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a ArrayRef> {
    batch
        .column_by_name(name)
        .ok_or_else(|| DataFusionError::Execution(format!("missing column {name}")))
}

/// An integer column widened to 64 bits.
fn integers(batch: &RecordBatch, name: &str) -> Result<Int64Array> {
    let array = cast(column(batch, name)?, &DataType::Int64)?;
    Ok(array.as_primitive().clone())
}

/// Stored JSON text passed through unparsed. Missing or invalid JSON becomes
/// the given default, as the raw span API has always done.
fn raw_json(text: Option<&str>, default: &'static str) -> Box<RawValue> {
    text.and_then(|text| serde_json::from_str::<Box<RawValue>>(text).ok())
        .unwrap_or_else(|| {
            RawValue::from_string(default.to_string()).expect("default is valid JSON")
        })
}

fn span_kind_name(kind: i64) -> &'static str {
    match kind {
        1 => "INTERNAL",
        2 => "SERVER",
        3 => "CLIENT",
        4 => "PRODUCER",
        5 => "CONSUMER",
        _ => "UNSPECIFIED",
    }
}

fn append_spans(batch: &RecordBatch, spans: &mut Vec<Span>) -> Result<()> {
    let span_id = Text::column(batch, "span_id")?;
    let trace_id = Text::column(batch, "trace_id")?;
    let parent_span_id = Text::column(batch, "parent_span_id")?;
    let service_name = Text::column(batch, "service_name")?;
    let name = Text::column(batch, "name")?;
    let status_message = Text::column(batch, "status_message")?;
    let attributes = Text::column(batch, "attributes")?;
    let events = Text::column(batch, "events")?;
    let links = Text::column(batch, "links")?;
    let trace_state = Text::column(batch, "trace_state")?;
    let resource_attributes = Text::column(batch, "resource_attributes")?;
    let span_kind = integers(batch, "span_kind")?;
    let start_time_ns = integers(batch, "start_time_ns")?;
    let end_time_ns = integers(batch, "end_time_ns")?;
    let status_code = integers(batch, "status_code")?;
    let trace_flags = integers(batch, "trace_flags")?;
    let dropped_attributes_count = integers(batch, "dropped_attributes_count")?;
    let dropped_events_count = integers(batch, "dropped_events_count")?;
    let dropped_links_count = integers(batch, "dropped_links_count")?;
    let resource_dropped_attributes_count = integers(batch, "resource_dropped_attributes_count")?;
    let nanoseconds =
        |array: &Int64Array, row: usize| (!array.is_null(row)).then(|| array.value(row));

    spans.reserve(batch.num_rows());
    for row in 0..batch.num_rows() {
        spans.push(Span {
            trace_id: trace_id.value(row).unwrap_or_default().to_string(),
            span_id: span_id.value(row).unwrap_or_default().to_string(),
            parent_span_id: parent_span_id.value(row).map(str::to_string),
            service_name: service_name.value(row).unwrap_or_default().to_string(),
            name: name.value(row).unwrap_or_default().to_string(),
            kind: span_kind_name(span_kind.value(row)),
            start_time: format_span_timestamp(nanoseconds(&start_time_ns, row)),
            start_time_ns: nanoseconds(&start_time_ns, row),
            end_time: format_span_timestamp(nanoseconds(&end_time_ns, row)),
            status_code: status_code.value(row).to_string(),
            status_message: status_message.value(row).unwrap_or_default().to_string(),
            attributes_json: raw_json(attributes.value(row), "{}"),
            events_json: raw_json(events.value(row), "[]"),
            links_json: raw_json(links.value(row), "[]"),
            trace_flags: trace_flags.value(row),
            trace_state: trace_state.value(row).map(str::to_string),
            dropped_attributes_count: dropped_attributes_count.value(row),
            dropped_events_count: dropped_events_count.value(row),
            dropped_links_count: dropped_links_count.value(row),
            resource_attributes_json: raw_json(resource_attributes.value(row), "{}"),
            resource_dropped_attributes_count: resource_dropped_attributes_count.value(row),
        });
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use junjo_evidence::agent_diagnostics::assembler::assemble_agent_detail;
    use serde_json::json;

    use super::*;
    use crate::test_support::{
        TestSpan, api_spans, case_spans, datafusion_config, telemetry_fixtures, write_span_parquet,
    };

    /// A page size larger than any data these tests write.
    const LARGE_PAGE: usize = 250;

    struct Fixture {
        directory: tempfile::TempDir,
        engine: QueryEngine,
    }

    fn fixture() -> Fixture {
        let directory = tempfile::tempdir().unwrap();
        let engine = QueryEngine::new(&datafusion_config(directory.path())).unwrap();
        Fixture { directory, engine }
    }

    impl Fixture {
        fn write(&self, name: &str, spans: &[TestSpan]) -> String {
            let path: PathBuf = self.directory.path().join(name);
            write_span_parquet(&path, spans);
            path.to_str().unwrap().to_string()
        }

        /// Write the spans of one shared telemetry fixture as ingestion would
        /// store them.
        fn write_case(&self, name: &str, case: &Json) -> String {
            let spans: Vec<TestSpan> = case["spans"]
                .as_array()
                .unwrap()
                .iter()
                .map(TestSpan::from_api_span)
                .collect();
            self.write(name, &spans)
        }
    }

    fn cold_only(file: &str) -> QuerySources {
        QuerySources {
            cold_files: vec![file.to_string()],
            hot_snapshot: None,
        }
    }

    fn hot_only(file: &str) -> QuerySources {
        QuerySources {
            cold_files: Vec::new(),
            hot_snapshot: Some(file.to_string()),
        }
    }

    fn span_ids(spans: &[Span]) -> Vec<&str> {
        spans.iter().map(|span| span.span_id.as_str()).collect()
    }

    /// The first page of a walk with no bounds.
    fn first_page(limit: usize) -> AgentSpanPage {
        AgentSpanPage {
            indexed_files: Vec::new(),
            bounds: AgentSpanBounds::default(),
            after: None,
            started_after_ns: None,
            limit,
        }
    }

    fn agent(trace_id: &str, span_id: &str, start_time_ns: i64) -> TestSpan {
        TestSpan::new(trace_id, span_id, "checkout")
            .times(start_time_ns, start_time_ns + 10)
            .attributes(r#"{"junjo.span_type":"agent"}"#)
    }

    fn names(spans: &[Span]) -> Vec<&str> {
        spans.iter().map(|span| span.name.as_str()).collect()
    }

    /// Every valid Agent fixture: the producer and the consumer scenarios,
    /// named by their directory so no two share a name.
    fn agent_cases() -> Vec<(String, Json)> {
        let mut cases = Vec::new();
        for directory in ["producer", "consumer"] {
            for (name, case) in telemetry_fixtures(&format!("agent/{directory}")) {
                cases.push((format!("{directory}-{name}"), case));
            }
        }
        cases
    }

    /// No query result depends on this, so only this test notices if the
    /// engine goes back to decoding every row before it filters.
    #[test]
    fn filters_are_applied_while_parquet_is_decoded() {
        let parquet = fixture()
            .engine
            .session_config
            .options()
            .execution
            .parquet
            .clone();
        assert!(parquet.pushdown_filters);
        assert!(parquet.reorder_filters);
    }

    #[tokio::test]
    async fn a_cold_only_trace_query_returns_the_trace_newest_first() {
        let fixture = fixture();
        let cold = fixture.write(
            "cold.parquet",
            &[
                TestSpan::new("trace-1", "span-1", "checkout").times(1_000_000_000, 2_000_000_000),
                TestSpan::new("trace-1", "span-2", "checkout").times(3_000_000_000, 4_000_000_000),
                TestSpan::new("trace-2", "span-3", "checkout").times(5_000_000_000, 6_000_000_000),
            ],
        );
        let sources = QuerySources {
            cold_files: vec![cold],
            hot_snapshot: None,
        };

        let spans = fixture
            .engine
            .trace_spans(&sources, "trace-1")
            .await
            .unwrap();

        let ids: Vec<&str> = spans.iter().map(|span| span.span_id.as_str()).collect();
        assert_eq!(ids, ["span-2", "span-1"]);
        assert_eq!(spans[0].start_time, "1970-01-01T00:00:03.000000+00:00");
        assert_eq!(spans[0].end_time, "1970-01-01T00:00:04.000000+00:00");
        assert_eq!(spans[0].kind, "INTERNAL");
        assert_eq!(spans[0].status_code, "0");
        assert_eq!(spans[0].status_message, "");
        assert_eq!(spans[0].parent_span_id, None);
        assert_eq!(spans[0].trace_state, None);
        assert_eq!(spans[0].trace_flags, 0);
    }

    #[tokio::test]
    async fn cold_takes_precedence_over_hot_for_the_same_span() {
        let fixture = fixture();
        let cold = fixture.write(
            "cold.parquet",
            &[TestSpan::new("trace-1", "span-1", "checkout").name("from-cold")],
        );
        let hot = fixture.write(
            "hot_snapshot.parquet",
            &[
                TestSpan::new("trace-1", "span-1", "checkout").name("from-hot"),
                TestSpan::new("trace-1", "span-2", "checkout").name("hot-only"),
            ],
        );
        let sources = QuerySources {
            cold_files: vec![cold],
            hot_snapshot: Some(hot),
        };

        let mut spans = fixture
            .engine
            .trace_spans(&sources, "trace-1")
            .await
            .unwrap();

        spans.sort_by(|left, right| left.span_id.cmp(&right.span_id));
        let names: Vec<(&str, &str)> = spans
            .iter()
            .map(|span| (span.span_id.as_str(), span.name.as_str()))
            .collect();
        assert_eq!(names, [("span-1", "from-cold"), ("span-2", "hot-only")]);
    }

    #[tokio::test]
    async fn a_hot_only_query_reads_the_snapshot() {
        let fixture = fixture();
        let hot = fixture.write(
            "hot_snapshot.parquet",
            &[TestSpan::new("trace-1", "span-1", "checkout")],
        );
        let sources = QuerySources {
            cold_files: Vec::new(),
            hot_snapshot: Some(hot),
        };
        let spans = fixture
            .engine
            .trace_spans(&sources, "trace-1")
            .await
            .unwrap();
        assert_eq!(spans.len(), 1);
    }

    #[tokio::test]
    async fn stored_json_is_passed_through_and_invalid_json_becomes_the_default() {
        let fixture = fixture();
        let mut invalid = TestSpan::new("trace-1", "span-2", "checkout").attributes("not json");
        invalid.events = "also not json".to_string();
        let cold = fixture.write(
            "cold.parquet",
            &[
                TestSpan::new("trace-1", "span-1", "checkout")
                    .attributes(r#"{"zeta":1,"alpha":{"nested":[1.50,"日本語"]}}"#),
                invalid,
            ],
        );
        let sources = QuerySources {
            cold_files: vec![cold],
            hot_snapshot: None,
        };

        let mut spans = fixture
            .engine
            .trace_spans(&sources, "trace-1")
            .await
            .unwrap();

        spans.sort_by(|left, right| left.span_id.cmp(&right.span_id));
        // Key order and number formatting are exactly what ingestion stored.
        assert_eq!(
            spans[0].attributes_json.get(),
            r#"{"zeta":1,"alpha":{"nested":[1.50,"日本語"]}}"#
        );
        assert_eq!(
            spans[0].resource_attributes_json.get(),
            r#"{"service.name":"test"}"#
        );
        assert_eq!(spans[1].attributes_json.get(), "{}");
        assert_eq!(spans[1].events_json.get(), "[]");
        let body = serde_json::to_string(&spans[0]).unwrap();
        assert!(
            body.contains(r#""attributes_json":{"zeta":1,"alpha""#),
            "{body}"
        );
    }

    #[tokio::test]
    async fn the_trace_identifier_is_bound_as_a_value() {
        let fixture = fixture();
        let cold = fixture.write(
            "cold.parquet",
            &[TestSpan::new("trace-1", "span-1", "checkout")],
        );
        let sources = QuerySources {
            cold_files: vec![cold],
            hot_snapshot: None,
        };
        let spans = fixture
            .engine
            .trace_spans(&sources, "' OR '1'='1")
            .await
            .unwrap();
        assert!(spans.is_empty());
    }

    #[tokio::test]
    async fn distinct_services_cover_both_tiers_without_duplicates() {
        let fixture = fixture();
        let recent = fixture.write(
            "recent.parquet",
            &[
                TestSpan::new("trace-1", "span-1", "checkout"),
                TestSpan::new("trace-2", "span-2", "billing"),
            ],
        );
        let hot = fixture.write(
            "hot_snapshot.parquet",
            &[
                TestSpan::new("trace-3", "span-3", "checkout"),
                TestSpan::new("trace-4", "span-4", "search"),
            ],
        );
        let sources = QuerySources {
            cold_files: vec![recent],
            hot_snapshot: Some(hot),
        };
        assert_eq!(
            fixture
                .engine
                .distinct_service_names(&sources)
                .await
                .unwrap(),
            ["billing", "checkout", "search"]
        );
    }

    #[tokio::test]
    async fn unusable_files_are_skipped_instead_of_failing_the_query() {
        let fixture = fixture();
        let good = fixture.write(
            "good.parquet",
            &[TestSpan::new("trace-1", "span-1", "checkout")],
        );
        let corrupt = fixture.directory.path().join("corrupt.parquet");
        std::fs::write(&corrupt, b"not parquet").unwrap();
        let empty = fixture.directory.path().join("empty.parquet");
        std::fs::write(&empty, b"").unwrap();
        let sources = QuerySources {
            cold_files: vec![
                corrupt.to_str().unwrap().to_string(),
                good.clone(),
                empty.to_str().unwrap().to_string(),
                fixture
                    .directory
                    .path()
                    .join("missing.parquet")
                    .to_str()
                    .unwrap()
                    .to_string(),
                good,
            ],
            hot_snapshot: None,
        };

        let spans = fixture
            .engine
            .trace_spans(&sources, "trace-1")
            .await
            .unwrap();

        assert_eq!(spans.len(), 1);
    }

    /// Registration reads only the first file's footer, so a damaged file
    /// later in the list is found when the query runs, not when it is
    /// registered.
    #[tokio::test]
    async fn a_corrupt_file_after_a_readable_one_is_skipped() {
        let fixture = fixture();
        let good = fixture.write(
            "good.parquet",
            &[TestSpan::new("trace-1", "span-1", "checkout")],
        );
        let corrupt = fixture.directory.path().join("corrupt.parquet");
        std::fs::write(&corrupt, b"not parquet").unwrap();
        let sources = QuerySources {
            cold_files: vec![good, corrupt.to_str().unwrap().to_string()],
            hot_snapshot: None,
        };

        let spans = fixture
            .engine
            .trace_spans(&sources, "trace-1")
            .await
            .unwrap();

        assert_eq!(spans.len(), 1);
    }

    #[tokio::test]
    async fn no_usable_sources_is_an_empty_result() {
        let fixture = fixture();
        let sources = QuerySources::default();
        assert!(
            fixture
                .engine
                .trace_spans(&sources, "trace-1")
                .await
                .unwrap()
                .is_empty()
        );
        assert!(
            fixture
                .engine
                .distinct_service_names(&sources)
                .await
                .unwrap()
                .is_empty()
        );
    }

    #[tokio::test]
    async fn only_unusable_files_is_an_empty_result() {
        let fixture = fixture();
        let empty = fixture.directory.path().join("empty.parquet");
        std::fs::write(&empty, b"").unwrap();

        let spans = fixture
            .engine
            .trace_spans(&cold_only(empty.to_str().unwrap()), "trace-1")
            .await
            .unwrap();

        assert!(spans.is_empty());
    }

    #[tokio::test]
    async fn span_kinds_use_the_canonical_otlp_names() {
        let fixture = fixture();
        let kinds: [(i8, &str); 7] = [
            (0, "UNSPECIFIED"),
            (1, "INTERNAL"),
            (2, "SERVER"),
            (3, "CLIENT"),
            (4, "PRODUCER"),
            (5, "CONSUMER"),
            (99, "UNSPECIFIED"),
        ];
        let stored: Vec<TestSpan> = kinds
            .iter()
            .map(|(kind, _)| {
                let mut span = TestSpan::new("trace-1", &format!("span-{kind}"), "checkout");
                span.span_kind = *kind;
                span
            })
            .collect();
        let cold = fixture.write("cold.parquet", &stored);

        let spans = fixture
            .engine
            .trace_spans(&cold_only(&cold), "trace-1")
            .await
            .unwrap();

        assert_eq!(spans.len(), kinds.len());
        for (kind, expected) in kinds {
            let span = spans
                .iter()
                .find(|span| span.span_id == format!("span-{kind}"))
                .unwrap();
            assert_eq!(span.kind, expected, "span kind {kind}");
        }
    }

    #[tokio::test]
    async fn a_trace_spread_over_several_cold_files_is_read_from_all_of_them() {
        let fixture = fixture();
        let first = fixture.write(
            "a.parquet",
            &[TestSpan::new("trace-1", "span-1", "checkout").name("a")],
        );
        let second = fixture.write(
            "b.parquet",
            &[TestSpan::new("trace-1", "span-2", "checkout").name("b")],
        );
        let sources = QuerySources {
            cold_files: vec![first, second],
            hot_snapshot: None,
        };

        let mut spans = fixture
            .engine
            .trace_spans(&sources, "trace-1")
            .await
            .unwrap();

        spans.sort_by(|left, right| left.name.cmp(&right.name));
        assert_eq!(names(&spans), ["a", "b"]);
    }

    #[tokio::test]
    async fn distinct_services_in_one_file_are_listed_once_in_order() {
        let fixture = fixture();
        let cold = fixture.write(
            "cold.parquet",
            &[
                TestSpan::new("trace-1", "span-1", "beta"),
                TestSpan::new("trace-1", "span-2", "alpha"),
                TestSpan::new("trace-1", "span-3", "beta"),
            ],
        );

        assert_eq!(
            fixture
                .engine
                .distinct_service_names(&cold_only(&cold))
                .await
                .unwrap(),
            ["alpha", "beta"]
        );
    }

    #[tokio::test]
    async fn a_service_query_returns_its_newest_spans_from_both_tiers_up_to_the_limit() {
        let fixture = fixture();
        let cold = fixture.write(
            "cold.parquet",
            &[
                TestSpan::new("trace-1", "span-1", "checkout").times(1_000, 2_000),
                TestSpan::new("trace-2", "span-2", "checkout").times(3_000, 4_000),
                TestSpan::new("trace-3", "span-3", "billing").times(5_000, 6_000),
            ],
        );
        let hot = fixture.write(
            "hot_snapshot.parquet",
            &[
                TestSpan::new("trace-4", "span-4", "checkout").times(7_000, 8_000),
                // Already flushed as well: it is returned once.
                TestSpan::new("trace-2", "span-2", "checkout").times(3_000, 4_000),
            ],
        );
        let sources = QuerySources {
            cold_files: vec![cold],
            hot_snapshot: Some(hot),
        };

        let page = fixture
            .engine
            .service_spans(&sources, "checkout", 2, None)
            .await
            .unwrap();
        assert_eq!(span_ids(&page), ["span-4", "span-2"]);

        let all = fixture
            .engine
            .service_spans(&sources, "checkout", LARGE_PAGE, None)
            .await
            .unwrap();
        assert_eq!(span_ids(&all), ["span-4", "span-2", "span-1"]);

        // The service name is a bound value, not SQL text.
        let injected = fixture
            .engine
            .service_spans(&sources, "' OR '1'='1", LARGE_PAGE, None)
            .await
            .unwrap();
        assert!(injected.is_empty());
    }

    #[tokio::test]
    async fn a_listing_for_one_api_key_returns_only_the_spans_that_key_sent() {
        let fixture = fixture();
        let workflow = r#"{"junjo.span_type":"workflow"}"#;
        let cold = fixture.write(
            "cold.parquet",
            &[
                TestSpan::new("trace-1", "span-1", "checkout")
                    .times(1_000, 2_000)
                    .api_key("key-a"),
                TestSpan::new("trace-2", "span-2", "checkout")
                    .times(3_000, 4_000)
                    .api_key("key-b"),
            ],
        );
        let hot = fixture.write(
            "hot_snapshot.parquet",
            &[
                TestSpan::new("trace-3", "span-3", "checkout")
                    .times(5_000, 6_000)
                    .attributes(workflow)
                    .api_key("key-a"),
                TestSpan::new("trace-4", "span-4", "checkout")
                    .times(7_000, 8_000)
                    .attributes(workflow)
                    .api_key("key-b"),
            ],
        );
        let sources = QuerySources {
            cold_files: vec![cold],
            hot_snapshot: Some(hot),
        };
        let engine = &fixture.engine;
        let key_a = Some("key-a");

        let spans = engine.service_spans(&sources, "checkout", LARGE_PAGE, key_a);
        assert_eq!(span_ids(&spans.await.unwrap()), ["span-3", "span-1"]);
        let roots = engine.root_spans(&sources, "checkout", LARGE_PAGE, key_a);
        assert_eq!(span_ids(&roots.await.unwrap()), ["span-3", "span-1"]);
        let workflows = engine.workflow_spans(&sources, "checkout", LARGE_PAGE, key_a);
        assert_eq!(span_ids(&workflows.await.unwrap()), ["span-3"]);

        // Without a key every span is listed, and the identifier is a bound
        // value, not SQL text.
        let every = engine.service_spans(&sources, "checkout", LARGE_PAGE, None);
        assert_eq!(every.await.unwrap().len(), 4);
        let injected = engine.service_spans(&sources, "checkout", LARGE_PAGE, Some("' OR '1'='1"));
        assert!(injected.await.unwrap().is_empty());
    }

    #[tokio::test]
    async fn the_same_span_identifier_in_two_traces_is_two_spans() {
        // A span identifier is unique only within its trace, so the tiers are
        // deduplicated by trace and span together.
        let fixture = fixture();
        let cold = fixture.write(
            "cold.parquet",
            &[TestSpan::new("trace-cold", "shared-span", "checkout").name("cold-trace-span")],
        );
        let hot = fixture.write(
            "hot_snapshot.parquet",
            &[TestSpan::new("trace-hot", "shared-span", "checkout").name("hot-trace-span")],
        );
        let sources = QuerySources {
            cold_files: vec![cold],
            hot_snapshot: Some(hot),
        };

        let mut spans = fixture
            .engine
            .service_spans(&sources, "checkout", LARGE_PAGE, None)
            .await
            .unwrap();

        spans.sort_by(|left, right| left.trace_id.cmp(&right.trace_id));
        let identities: Vec<(&str, &str, &str)> = spans
            .iter()
            .map(|span| {
                (
                    span.trace_id.as_str(),
                    span.span_id.as_str(),
                    span.name.as_str(),
                )
            })
            .collect();
        assert_eq!(
            identities,
            [
                ("trace-cold", "shared-span", "cold-trace-span"),
                ("trace-hot", "shared-span", "hot-trace-span"),
            ]
        );
    }

    #[tokio::test]
    async fn root_spans_are_the_spans_of_a_service_without_a_parent() {
        let fixture = fixture();
        let cold = fixture.write(
            "cold.parquet",
            &[
                TestSpan::new("trace-1", "span-1", "checkout")
                    .name("root")
                    .times(1_000, 2_000),
                TestSpan::new("trace-1", "span-2", "checkout")
                    .name("child")
                    .parent("span-1")
                    .times(3_000, 4_000),
                // An empty parent is read as no parent.
                TestSpan::new("trace-2", "span-3", "checkout")
                    .name("empty-parent")
                    .parent("")
                    .times(5_000, 6_000),
                TestSpan::new("trace-3", "span-4", "billing")
                    .name("other-service")
                    .times(7_000, 8_000),
            ],
        );
        let sources = cold_only(&cold);

        let roots = fixture
            .engine
            .root_spans(&sources, "checkout", LARGE_PAGE, None)
            .await
            .unwrap();
        assert_eq!(names(&roots), ["empty-parent", "root"]);
        assert_eq!(roots[0].parent_span_id.as_deref(), Some(""));
        assert_eq!(roots[1].parent_span_id, None);

        let newest = fixture
            .engine
            .root_spans(&sources, "checkout", 1, None)
            .await
            .unwrap();
        assert_eq!(names(&newest), ["empty-parent"]);
    }

    #[tokio::test]
    async fn workflow_and_agent_queries_check_the_parsed_span_type() {
        let fixture = fixture();
        let cold = fixture.write(
            "cold.parquet",
            &[
                TestSpan::new("trace-1", "workflow", "checkout")
                    .attributes(r#"{"junjo.span_type":"workflow"}"#),
                TestSpan::new("trace-1", "agent", "checkout")
                    .attributes(r#"{"junjo.span_type":"agent"}"#),
                // The substring prefilter matches these two. The exact check
                // does not: the member belongs to a nested value.
                TestSpan::new("trace-1", "nested-workflow", "checkout").attributes(
                    r#"{"junjo.span_type":"node","payload":{"junjo.span_type":"workflow"}}"#,
                ),
                TestSpan::new("trace-1", "nested-agent", "checkout")
                    .attributes(r#"{"payload":{"junjo.span_type":"agent"}}"#),
                TestSpan::new("trace-2", "other-service", "billing")
                    .attributes(r#"{"junjo.span_type":"workflow"}"#),
            ],
        );
        let sources = cold_only(&cold);

        let workflows = fixture
            .engine
            .workflow_spans(&sources, "checkout", LARGE_PAGE, None)
            .await
            .unwrap();
        assert_eq!(span_ids(&workflows), ["workflow"]);

        // An Agent page is the prefilter's spans. The walk makes the exact
        // check: it continues after the page's last span, whatever it is.
        let agents = fixture
            .engine
            .agent_spans(&sources, "checkout", &first_page(LARGE_PAGE))
            .await
            .unwrap();
        assert_eq!(span_ids(&agents), ["agent", "nested-agent"]);
    }

    #[tokio::test]
    async fn an_agent_page_holds_the_spans_after_a_place_inside_its_bounds() {
        let fixture = fixture();
        let cold = fixture.write(
            "cold.parquet",
            &[
                agent("trace-1", "at-500", 500),
                // Three spans start together. Their order is by trace and
                // then by span identifier.
                agent("trace-2", "b", 400),
                agent("trace-1", "z", 400),
                agent("trace-2", "a", 400),
                agent("trace-1", "at-300", 300),
                agent("trace-1", "at-200", 200),
                TestSpan::new("trace-1", "not-an-agent", "checkout").times(450, 460),
            ],
        );
        let sources = cold_only(&cold);
        let page = |page: AgentSpanPage| {
            let (engine, sources) = (&fixture.engine, &sources);
            async move {
                let spans = engine.agent_spans(sources, "checkout", &page).await;
                let spans = spans.unwrap();
                spans
                    .iter()
                    .map(|span| span.span_id.clone())
                    .collect::<Vec<_>>()
            }
        };
        let place = |start_time_ns, span: Option<(&str, &str)>| {
            Some(SpanPlace {
                start_time_ns,
                span: span.map(|(trace_id, span_id)| (trace_id.to_string(), span_id.to_string())),
            })
        };

        assert_eq!(page(first_page(3)).await, ["at-500", "z", "a"]);
        // After a span: the rest of the spans that start with it, then
        // the older ones.
        let after_a = AgentSpanPage {
            after: place(400, Some(("trace-2", "a"))),
            ..first_page(3)
        };
        assert_eq!(page(after_a).await, ["b", "at-300", "at-200"]);
        // A place with no span is before every span that starts at its time.
        let from_400 = AgentSpanPage {
            after: place(400, None),
            ..first_page(2)
        };
        assert_eq!(page(from_400).await, ["z", "a"]);
        // A page stops above the time older files can reach.
        let above_300 = AgentSpanPage {
            started_after_ns: Some(300),
            ..first_page(LARGE_PAGE)
        };
        assert_eq!(page(above_300).await, ["at-500", "z", "a", "b"]);
        // The caller's bounds: started at or after, ended at or before.
        let bounded = AgentSpanPage {
            bounds: AgentSpanBounds {
                started_from_ns: Some(300),
                ended_by_ns: Some(410),
                ..AgentSpanBounds::default()
            },
            ..first_page(LARGE_PAGE)
        };
        assert_eq!(page(bounded).await, ["z", "a", "b", "at-300"]);
    }

    #[tokio::test]
    async fn an_agent_page_holds_the_spans_whose_stored_text_contains_what_the_caller_wants() {
        let fixture = fixture();
        let stored = |span_id: &str, start_time_ns, key: &str, version: &str| {
            let mut span = TestSpan::new("trace-1", span_id, "checkout")
                .times(start_time_ns, start_time_ns + 10)
                .attributes(&format!(
                    r#"{{"junjo.span_type":"agent","junjo.agent.key":"{key}"}}"#
                ));
            span.resource_attributes = format!(r#"{{"service.version":"{version}"}}"#);
            span
        };
        let cold = fixture.write(
            "cold.parquet",
            &[
                stored("wanted", 500, "50%_off", "2.0.0"),
                // `%` and `_` are text here, not wildcards.
                stored("other-key", 400, "50x-off", "2.0.0"),
                stored("other-version", 300, "50%_off", "1.0.0"),
            ],
        );
        let page = AgentSpanPage {
            bounds: AgentSpanBounds {
                attributes_contain: vec![r#""junjo.agent.key":"50%_off""#.to_string()],
                resource_attributes_contain: vec![r#""service.version":"2.0.0""#.to_string()],
                ..AgentSpanBounds::default()
            },
            ..first_page(LARGE_PAGE)
        };

        let spans = fixture
            .engine
            .agent_spans(&cold_only(&cold), "checkout", &page)
            .await
            .unwrap();

        assert_eq!(span_ids(&spans), ["wanted"]);
    }

    #[tokio::test]
    async fn an_agent_page_is_not_shortened_by_a_span_stored_twice_in_one_tier() {
        let fixture = fixture();
        // The newest span is in two cold files. The hot snapshot holds a
        // copy of a flushed span and one span of its own.
        let cold = fixture.write(
            "cold.parquet",
            &[
                agent("trace-1", "twice", 500).name("cold"),
                agent("trace-1", "flushed", 400).name("cold"),
                agent("trace-1", "older", 300).name("cold"),
            ],
        );
        let copy = fixture.write(
            "copy.parquet",
            &[agent("trace-1", "twice", 500).name("cold")],
        );
        let hot = fixture.write(
            "hot.parquet",
            &[
                agent("trace-1", "flushed", 400).name("hot"),
                agent("trace-1", "unflushed", 600).name("hot"),
            ],
        );
        let sources = QuerySources {
            cold_files: vec![cold, copy],
            hot_snapshot: Some(hot),
        };

        let spans = fixture
            .engine
            .agent_spans(&sources, "checkout", &first_page(4))
            .await
            .unwrap();

        // A full page: the walk continues after it and reaches "older".
        assert_eq!(span_ids(&spans), ["unflushed", "twice", "twice", "flushed"]);
        assert_eq!(names(&spans), ["hot", "cold", "cold", "cold"]);
    }

    #[tokio::test]
    async fn a_workflow_page_counts_workflow_spans_not_arbitrary_spans() {
        let fixture = fixture();
        let cold = fixture.write(
            "cold.parquet",
            &[
                TestSpan::new("trace-1", "workflow-old", "checkout")
                    .times(1_000, 2_000)
                    .attributes(r#"{"junjo.span_type":"workflow"}"#),
                TestSpan::new("trace-2", "workflow-new", "checkout")
                    .times(3_000, 4_000)
                    .attributes(r#"{"junjo.span_type":"workflow"}"#),
                // Newer than both Workflow spans.
                TestSpan::new("trace-2", "node-1", "checkout")
                    .times(5_000, 6_000)
                    .attributes(r#"{"junjo.span_type":"node"}"#),
                TestSpan::new("trace-2", "node-2", "checkout").times(7_000, 8_000),
            ],
        );

        let page = fixture
            .engine
            .workflow_spans(&cold_only(&cold), "checkout", 2, None)
            .await
            .unwrap();

        assert_eq!(span_ids(&page), ["workflow-new", "workflow-old"]);
    }

    #[tokio::test]
    async fn an_executable_is_selected_by_its_exact_type_and_runtime_identity() {
        let fixture = fixture();
        let identity = |span_type: &str, runtime_id: Json| {
            json!({
                "junjo.telemetry.contract_version": 3,
                "junjo.span_type": span_type,
                "junjo.executable_runtime_id": runtime_id,
            })
            .to_string()
        };
        let cold = fixture.write(
            "cold.parquet",
            &[
                TestSpan::new("trace-1", "expected", "ai-chat")
                    .attributes(&identity("workflow", json!("run_100%"))),
                TestSpan::new("trace-1", "other-type", "ai-chat")
                    .attributes(&identity("agent", json!("run_100%"))),
                // As a `LIKE` pattern, the wanted identity would match this.
                TestSpan::new("trace-1", "other-run", "ai-chat")
                    .attributes(&identity("workflow", json!("run_1000"))),
                TestSpan::new("trace-1", "not-text", "ai-chat")
                    .attributes(&identity("workflow", json!(["run_100%"]))),
                TestSpan::new("trace-1", "nested", "ai-chat").attributes(
                    &json!({"payload": {
                        "junjo.span_type": "workflow",
                        "junjo.executable_runtime_id": "run_100%",
                    }})
                    .to_string(),
                ),
                TestSpan::new("trace-2", "other-service", "billing")
                    .attributes(&identity("workflow", json!("run_100%"))),
                // Valid JSON that is not compact still names its executable.
                TestSpan::new("trace-3", "spaced", "spaced-service").attributes(
                    r#"{ "junjo.span_type" : "workflow", "junjo.executable_runtime_id" : "run_100%" }"#,
                ),
            ],
        );
        let sources = cold_only(&cold);

        let spans = fixture
            .engine
            .executable_spans(&sources, "ai-chat", "workflow", "run_100%")
            .await
            .unwrap();
        assert_eq!(span_ids(&spans), ["expected"]);

        let spaced = fixture
            .engine
            .executable_spans(&sources, "spaced-service", "workflow", "run_100%")
            .await
            .unwrap();
        assert_eq!(span_ids(&spaced), ["spaced"]);
    }

    #[tokio::test]
    async fn a_single_span_is_found_by_trace_and_span_identifier() {
        let fixture = fixture();
        let cold = fixture.write(
            "cold.parquet",
            &[
                TestSpan::new("trace-1", "span-1", "checkout").name("from-cold"),
                TestSpan::new("trace-1", "span-2", "checkout").name("sibling"),
                TestSpan::new("trace-2", "span-1", "checkout").name("other-trace"),
            ],
        );
        let hot = fixture.write(
            "hot_snapshot.parquet",
            &[
                TestSpan::new("trace-1", "span-1", "checkout").name("from-hot"),
                TestSpan::new("trace-1", "span-3", "checkout").name("hot-only"),
            ],
        );
        let sources = QuerySources {
            cold_files: vec![cold],
            hot_snapshot: Some(hot),
        };
        let engine = &fixture.engine;

        let in_both_tiers = engine.span(&sources, "trace-1", "span-1").await.unwrap();
        assert_eq!(in_both_tiers.unwrap().name, "from-cold");
        let in_hot_only = engine.span(&sources, "trace-1", "span-3").await.unwrap();
        assert_eq!(in_hot_only.unwrap().name, "hot-only");
        let in_other_trace = engine.span(&sources, "trace-2", "span-1").await.unwrap();
        assert_eq!(in_other_trace.unwrap().name, "other-trace");

        let unknown_span = engine.span(&sources, "trace-1", "missing").await.unwrap();
        assert!(unknown_span.is_none());
        let unknown_trace = engine.span(&sources, "missing", "span-1").await.unwrap();
        assert!(unknown_trace.is_none());
    }

    const OPENINFERENCE_LLM: &str = r#"{"openinference.span.kind":"LLM"}"#;

    fn trace_ids(names: &[&str]) -> HashSet<String> {
        names.iter().map(|name| name.to_string()).collect()
    }

    #[tokio::test]
    async fn llm_traces_are_found_among_the_candidates_in_the_unindexed_spans_of_one_service() {
        let fixture = fixture();
        let hot = fixture.write(
            "hot_snapshot.parquet",
            &[
                TestSpan::new("openinference", "span-1", "checkout").attributes(OPENINFERENCE_LLM),
                TestSpan::new("genai", "span-2", "checkout")
                    .attributes(r#"{"gen_ai.provider.name":"xai","gen_ai.operation.name":"chat"}"#),
                TestSpan::new("chain", "span-3", "checkout")
                    .attributes(r#"{"openinference.span.kind":"CHAIN"}"#),
                TestSpan::new("other-service", "span-4", "billing").attributes(OPENINFERENCE_LLM),
                TestSpan::new("not-a-candidate", "span-5", "checkout")
                    .attributes(OPENINFERENCE_LLM),
            ],
        );
        // A flushed file the indexer has not reached.
        let flushed = fixture.write(
            "flushed.parquet",
            &[
                TestSpan::new("flushed", "span-6", "checkout").attributes(OPENINFERENCE_LLM),
                TestSpan::new("chain", "span-7", "checkout"),
            ],
        );
        // A damaged file is skipped, as it is in a span query.
        let corrupt = fixture.directory.path().join("corrupt.parquet");
        std::fs::write(&corrupt, b"not parquet").unwrap();
        let unindexed = QuerySources {
            cold_files: vec![flushed, corrupt.to_str().unwrap().to_string()],
            hot_snapshot: Some(hot),
        };
        let candidates = trace_ids(&[
            "openinference",
            "genai",
            "chain",
            "other-service",
            "flushed",
        ]);

        let llm_trace_ids = fixture
            .engine
            .unindexed_llm_trace_ids(&unindexed, "checkout", &candidates, None)
            .await
            .unwrap();

        assert_eq!(
            llm_trace_ids,
            trace_ids(&["openinference", "genai", "flushed"])
        );
    }

    /// The listing passes the start of the oldest candidate root span. A span
    /// that started before it belongs to no candidate.
    #[tokio::test]
    async fn the_unindexed_llm_read_leaves_out_spans_that_started_before_its_bound() {
        let fixture = fixture();
        let llm_span = |trace_id: &str, start_time_ns: i64| {
            TestSpan::new(trace_id, &format!("{trace_id}-llm"), "checkout")
                .times(start_time_ns, start_time_ns + 100)
                .attributes(OPENINFERENCE_LLM)
        };
        let unindexed = QuerySources {
            cold_files: vec![fixture.write(
                "flushed.parquet",
                &[
                    llm_span("flushed-before", 4_999),
                    llm_span("flushed-after", 7_000),
                ],
            )],
            hot_snapshot: Some(fixture.write(
                "hot_snapshot.parquet",
                &[
                    llm_span("hot-before", 1_000),
                    llm_span("hot-at-the-bound", 5_000),
                ],
            )),
        };
        let candidates = trace_ids(&[
            "flushed-before",
            "flushed-after",
            "hot-before",
            "hot-at-the-bound",
        ]);
        let engine = &fixture.engine;

        let bounded = engine
            .unindexed_llm_trace_ids(&unindexed, "checkout", &candidates, Some(5_000))
            .await
            .unwrap();
        assert_eq!(bounded, trace_ids(&["flushed-after", "hot-at-the-bound"]));

        let unbounded = engine
            .unindexed_llm_trace_ids(&unindexed, "checkout", &candidates, None)
            .await
            .unwrap();
        assert_eq!(unbounded, candidates);
    }

    /// Ingestion removes the snapshot when its log is flushed. The spans it
    /// held are then in a cold file the query was not given, so the query
    /// fails instead of answering without them.
    #[tokio::test]
    async fn a_named_hot_snapshot_that_is_gone_fails_the_query() {
        let fixture = fixture();
        let cold = fixture.write(
            "cold.parquet",
            &[TestSpan::new("trace-1", "span-1", "checkout")],
        );
        let gone = fixture.directory.path().join("hot_snapshot.parquet");
        let gone = gone.to_str().unwrap();
        let sources = QuerySources {
            cold_files: vec![cold],
            hot_snapshot: Some(gone.to_string()),
        };
        let engine = &fixture.engine;

        let trace = SpanQuery::Trace {
            trace_id: "trace-1",
        };
        let error = engine.run(&sources, trace).await.unwrap_err();
        assert!(error.to_string().contains("cannot be read"), "{error}");
        let listing = SpanQuery::Service {
            service_name: "checkout",
            api_key_id: None,
            limit: LARGE_PAGE,
        };
        assert!(engine.run(&sources, listing).await.is_err());
        assert!(engine.distinct_service_names(&sources).await.is_err());
        let candidates = HashSet::from(["trace-1".to_string()]);
        let llm = engine.unindexed_llm_trace_ids(&sources, "checkout", &candidates, None);
        assert!(llm.await.is_err());

        // A snapshot that is there but is not Parquet fails the same way.
        std::fs::write(gone, b"not parquet").unwrap();
        assert!(engine.run(&sources, trace).await.is_err());
    }

    /// A listing removes duplicates among the newest spans of each tier. Its
    /// pages must be the pages of removing duplicates among every span.
    #[tokio::test]
    async fn a_listing_page_is_the_newest_spans_of_both_tiers_with_duplicates_removed() {
        let fixture = fixture();
        // 300 spans, each newer than the one before. Every fifth belongs to
        // another service, every third is a Workflow span, and every fourth
        // has a parent.
        let stored = |number: i64, tier: &str| {
            let service = if number % 5 == 0 {
                "billing"
            } else {
                "checkout"
            };
            let mut span = TestSpan::new(
                &format!("trace-{}", number / 4),
                &format!("span-{number:04}"),
                service,
            )
            .name(tier)
            .times(number * 1_000, number * 1_000 + 500);
            if number % 3 == 0 {
                span = span.attributes(r#"{"junjo.span_type":"workflow"}"#);
            }
            if number % 4 == 0 {
                span = span.parent("parent");
            }
            span
        };
        // Cold holds 0..200 in two files and hot holds 150..300, so 150..200
        // are in both tiers. A span's name says which copy was returned.
        let cold_a: Vec<TestSpan> = (0..100).map(|number| stored(number, "cold")).collect();
        let cold_b: Vec<TestSpan> = (100..200).map(|number| stored(number, "cold")).collect();
        let hot: Vec<TestSpan> = (150..300).map(|number| stored(number, "hot")).collect();
        let sources = QuerySources {
            cold_files: vec![
                fixture.write("a.parquet", &cold_a),
                fixture.write("b.parquet", &cold_b),
            ],
            hot_snapshot: Some(fixture.write("hot_snapshot.parquet", &hot)),
        };

        // The page a listing must return: the newest `limit` of the wanted
        // spans, each once, from cold when cold has it.
        let expected = |wanted: fn(i64) -> bool, limit: usize| -> Vec<(String, String)> {
            (0..300)
                .rev()
                .filter(|number| number % 5 != 0 && wanted(*number))
                .take(limit)
                .map(|number| {
                    let tier = if number < 200 { "cold" } else { "hot" };
                    (format!("span-{number:04}"), tier.to_string())
                })
                .collect()
        };
        let returned = |spans: Vec<Span>| -> Vec<(String, String)> {
            spans
                .into_iter()
                .map(|span| (span.span_id, span.name))
                .collect()
        };
        let engine = &fixture.engine;
        // Page sizes around each boundary: the hot-only spans, the spans in
        // both tiers, and everything.
        for limit in [1, 2, 7, 79, 80, 81, 119, 120, 121, 160, 239, 240, 241, 500] {
            let service = engine
                .service_spans(&sources, "checkout", limit, None)
                .await;
            assert_eq!(
                returned(service.unwrap()),
                expected(|_| true, limit),
                "service spans, limit {limit}"
            );
            let roots = engine.root_spans(&sources, "checkout", limit, None).await;
            assert_eq!(
                returned(roots.unwrap()),
                expected(|number| number % 4 != 0, limit),
                "root spans, limit {limit}"
            );
            let workflows = engine
                .workflow_spans(&sources, "checkout", limit, None)
                .await;
            assert_eq!(
                returned(workflows.unwrap()),
                expected(|number| number % 3 == 0, limit),
                "workflow spans, limit {limit}"
            );
        }
    }

    #[tokio::test]
    async fn evidence_parses_the_stored_json_columns() {
        let fixture = fixture();
        let mut stored = TestSpan::new("trace-1", "span-1", "checkout").attributes(
            r#"{"junjo.span_type":"workflow","other":"value","ratio":1.50,"nested":{"z":[1,"日本語"],"a":null}}"#,
        );
        stored.events = r#"[{"name":"set_state","timeUnixNano":"123","attributes":{"a":1},"droppedAttributesCount":0}]"#.to_string();
        stored.links = r#"[{"traceId":"trace-0","spanId":"span-0"}]"#.to_string();
        let cold = fixture.write("cold.parquet", &[stored]);

        let spans = fixture
            .engine
            .trace_spans(&cold_only(&cold), "trace-1")
            .await
            .unwrap();
        let evidence = spans[0].to_evidence();

        assert_eq!(evidence.attributes_json["junjo.span_type"], "workflow");
        assert_eq!(evidence.attributes_json["other"], "value");
        assert_eq!(evidence.events_json[0]["name"], "set_state");
        assert_eq!(evidence.events_json[0]["timeUnixNano"], "123");
        assert_eq!(evidence.links_json[0]["spanId"], "span-0");
        assert_eq!(evidence.resource_attributes_json["service.name"], "test");
        // Members keep the order they were stored in.
        let members: Vec<&String> = evidence.attributes_json.keys().collect();
        assert_eq!(members, ["junjo.span_type", "other", "ratio", "nested"]);
        // The parsed span is the span the raw API returns.
        assert_eq!(
            serde_json::to_value(&evidence).unwrap(),
            serde_json::to_value(&spans[0]).unwrap()
        );
    }

    #[tokio::test]
    async fn evidence_reads_a_json_column_of_the_wrong_kind_as_empty() {
        let fixture = fixture();
        let mut wrong_kinds = TestSpan::new("trace-1", "span-1", "checkout").attributes("[1,2]");
        wrong_kinds.events = r#"{"name":"not a list"}"#.to_string();
        wrong_kinds.links = r#""text""#.to_string();
        wrong_kinds.resource_attributes = "null".to_string();
        let mut invalid = TestSpan::new("trace-1", "span-2", "checkout").attributes("not json");
        invalid.events = "also not json".to_string();
        let cold = fixture.write("cold.parquet", &[wrong_kinds, invalid]);

        let mut spans = fixture
            .engine
            .trace_spans(&cold_only(&cold), "trace-1")
            .await
            .unwrap();
        spans.sort_by(|left, right| left.span_id.cmp(&right.span_id));

        // The raw span API passes valid JSON of any kind through.
        assert_eq!(spans[0].attributes_json.get(), "[1,2]");
        assert_eq!(spans[0].events_json.get(), r#"{"name":"not a list"}"#);
        assert_eq!(spans[0].links_json.get(), r#""text""#);
        assert_eq!(spans[0].resource_attributes_json.get(), "null");
        for span in &spans {
            let evidence = span.to_evidence();
            assert!(evidence.attributes_json.is_empty(), "{}", span.span_id);
            assert!(evidence.events_json.is_empty(), "{}", span.span_id);
            assert!(evidence.links_json.is_empty(), "{}", span.span_id);
        }
        assert!(spans[0].to_evidence().resource_attributes_json.is_empty());
    }

    #[tokio::test]
    async fn workflow_fixtures_round_trip_through_the_cold_tier_the_hot_tier_and_both() {
        let fixture = fixture();
        for (name, case) in telemetry_fixtures("workflow") {
            let file = fixture.write_case(&format!("{name}.parquet"), &case);
            let trace_id = case["trace_id"].as_str().unwrap();
            let both_tiers = QuerySources {
                cold_files: vec![file.clone()],
                hot_snapshot: Some(file.clone()),
            };

            for sources in [cold_only(&file), hot_only(&file), both_tiers] {
                let spans = fixture
                    .engine
                    .trace_spans(&sources, trace_id)
                    .await
                    .unwrap();
                assert_eq!(
                    api_spans(&spans),
                    case_spans(&case, None),
                    "{name} from {sources:?}"
                );
            }
        }
    }

    #[tokio::test]
    async fn the_workflow_query_finds_the_workflow_spans_of_every_workflow_fixture() {
        let fixture = fixture();
        for (name, case) in telemetry_fixtures("workflow") {
            let file = fixture.write_case(&format!("{name}.parquet"), &case);
            let service_name = case["service_name"].as_str().unwrap();

            let spans = fixture
                .engine
                .workflow_spans(&cold_only(&file), service_name, LARGE_PAGE, None)
                .await
                .unwrap();

            assert_eq!(
                api_spans(&spans),
                case_spans(&case, Some("workflow")),
                "{name}"
            );
        }
    }

    #[tokio::test]
    async fn agent_fixtures_round_trip_and_assemble_the_same_detail_from_parquet() {
        let fixture = fixture();
        for (name, case) in agent_cases() {
            let file = fixture.write_case(&format!("{name}.parquet"), &case);
            let sources = cold_only(&file);
            let trace_id = case["trace_id"].as_str().unwrap();
            let service_name = case["service_name"].as_str().unwrap();

            let trace = fixture
                .engine
                .trace_spans(&sources, trace_id)
                .await
                .unwrap();
            let mut owners = fixture
                .engine
                .agent_spans(&sources, service_name, &first_page(LARGE_PAGE))
                .await
                .unwrap();
            let expected_owners = case_spans(&case, Some("agent"));
            assert_eq!(api_spans(&trace), case_spans(&case, None), "{name}");
            assert_eq!(api_spans(&owners), expected_owners, "{name}");

            // The detail assembled from queried spans is the detail assembled
            // from the fixture itself.
            let expected_trace: Vec<&JsonObject> = case["spans"]
                .as_array()
                .unwrap()
                .iter()
                .map(|span| span.as_object().unwrap())
                .collect();
            let queried_trace: Vec<JsonObject> = trace
                .iter()
                .map(|span| span.to_evidence().to_object())
                .collect();
            let queried_trace: Vec<&JsonObject> = queried_trace.iter().collect();
            owners.sort_by(|left, right| left.span_id.cmp(&right.span_id));
            for (owner, expected_owner) in owners.iter().zip(&expected_owners) {
                assert_eq!(
                    assemble_agent_detail(&owner.to_evidence().to_object(), &queried_trace, None),
                    assemble_agent_detail(
                        expected_owner.as_object().unwrap(),
                        &expected_trace,
                        None
                    ),
                    "{name} owner {}",
                    owner.span_id
                );
            }
        }
    }

    #[tokio::test]
    async fn evidence_of_every_fixture_span_is_the_span_the_raw_api_returns() {
        let fixture = fixture();
        let mut cases = telemetry_fixtures("workflow");
        cases.extend(agent_cases());
        for (name, case) in cases {
            let file = fixture.write_case(&format!("{name}.parquet"), &case);
            let trace_id = case["trace_id"].as_str().unwrap();

            let spans = fixture
                .engine
                .trace_spans(&cold_only(&file), trace_id)
                .await
                .unwrap();

            assert!(!spans.is_empty(), "{name}");
            for span in &spans {
                let evidence = span.to_evidence();
                assert_eq!(
                    serde_json::to_value(&evidence).unwrap(),
                    serde_json::to_value(span).unwrap(),
                    "{name} span {}",
                    span.span_id
                );
                // Comparing the text also compares member order, which value
                // equality ignores.
                assert_eq!(
                    serde_json::to_string(&evidence).unwrap(),
                    serde_json::to_string(span).unwrap(),
                    "{name} span {}",
                    span.span_id
                );
            }
        }
    }
}
