//! Evaluation control: datasets, cases, runs, and attempts.
//!
//! Studio is the ledger of an evaluation. The application that owns the
//! evaluated code runs it and reports here: it creates a dataset of cases,
//! locks it, starts a run, binds each attempt to the execution it produced,
//! and records each result. Every write may be repeated, so an uncertain
//! caller retries without creating a second record (Studio ADR-010).
//!
//! A signed-in user may call every route. A developer access token needs the
//! evaluation read scope to read and the evaluation write scope to write.

use axum::Json;
use axum::extract::State;
use serde::Deserialize;
use serde_json::{Value, json};
use utoipa::IntoParams;
use utoipa_axum::router::OpenApiRouter;
use utoipa_axum::routes;

use crate::error::{ApiError, ApiJson, ApiPath, ApiQuery, ErrorResponse};
use crate::features::evaluation_tokens::access::{EvaluationReadAccess, EvaluationWriteAccess};
use crate::pagination::{
    Cursor, InvalidCursor, PageLimit, TimePosition, decode_cursor, decode_time_cursor,
    encode_cursor, encode_time_cursor, is_cursor_kind,
};
use crate::state::AppState;
use crate::timestamps::UtcSeconds;

pub mod repo;
pub mod schemas;

use repo::{MembershipPosition, Refusal};
// What other features read an attempt and its evidence through.
pub use schemas::{
    EvaluationAttemptDetail, EvaluationAttemptRead, ExecutableType, ExecutionEvidenceReference,
    OpenTelemetrySpanReference, RecordId, SemanticExecutionReference,
};
use schemas::{
    EvaluationAttemptResult, EvaluationCaseCreate, EvaluationCaseRead, EvaluationConflictResponse,
    EvaluationDatasetCreate, EvaluationDatasetDetail, EvaluationDatasetList, EvaluationDatasetRead,
    EvaluationEvidenceBind, EvaluationEvidenceMembershipList, EvaluationRunDetail,
    EvaluationRunList, EvaluationRunScope, EvaluationRunStart, EvidenceKind,
    EvidenceMembershipRole, ExecutionIdentityText, KeyText, NameText, OpenTelemetrySpanKind,
    SemanticExecutionKind, ServiceNamespaceText, SpanId, TargetKind, TraceId, Version,
};

/// Names each listing in its cursors.
const DATASETS_CURSOR_KIND: &str = "datasets";
const RUNS_CURSOR_KIND: &str = "runs";
const MEMBERSHIP_CURSOR_KIND: &str = "evidence-membership";

impl From<Refusal> for ApiError {
    fn from(refusal: Refusal) -> Self {
        match refusal {
            Refusal::NotFound(record) => ApiError::not_found(format!("{record} not found")),
            Refusal::Conflict { code, message } => ApiError::conflict(code, message),
        }
    }
}

/// Keep one page of a listing that was read one row past the page. Returns
/// whether another page follows.
fn keep_page<T>(items: &mut Vec<T>, limit: u32) -> bool {
    let has_more = items.len() > limit as usize;
    items.truncate(limit as usize);
    has_more
}

fn encode_membership_cursor(position: &MembershipPosition) -> String {
    encode_cursor(&json!({
        "v": 1,
        "kind": MEMBERSHIP_CURSOR_KIND,
        "role": position.role.as_str(),
        "id": position.record_id,
    }))
}

fn decode_membership_cursor(cursor: &Cursor) -> Result<MembershipPosition, InvalidCursor> {
    let members = decode_cursor(cursor)?;
    if !is_cursor_kind(&members, MEMBERSHIP_CURSOR_KIND) {
        return Err(InvalidCursor);
    }
    let role = match members.get("role").and_then(Value::as_str) {
        Some("case_source") => EvidenceMembershipRole::CaseSource,
        Some("attempt_subject") => EvidenceMembershipRole::AttemptSubject,
        _ => return Err(InvalidCursor),
    };
    let record_id = members
        .get("id")
        .and_then(Value::as_str)
        .filter(|id| !id.is_empty())
        .ok_or(InvalidCursor)?;
    Ok(MembershipPosition {
        role,
        record_id: record_id.to_string(),
    })
}

/// This feature's routes, relative to `/api/v1`.
pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(create_evaluation_dataset, list_evaluation_datasets))
        .routes(routes!(get_evaluation_dataset))
        .routes(routes!(add_evaluation_case))
        .routes(routes!(lock_evaluation_dataset))
        .routes(routes!(start_evaluation_run, list_evaluation_runs))
        .routes(routes!(get_evaluation_run))
        .routes(routes!(get_evaluation_attempt))
        .routes(routes!(bind_evaluation_attempt_evidence))
        .routes(routes!(record_evaluation_attempt_result))
        .routes(routes!(find_evaluation_evidence_membership))
}

/// Create a dataset.
///
/// A repeated request returns the dataset it created.
#[utoipa::path(
    post,
    path = "/evaluation/datasets",
    operation_id = "create_evaluation_dataset",
    tag = "evaluation",
    request_body = EvaluationDatasetCreate,
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "The dataset.", body = EvaluationDatasetRead),
        (status = 401, description = "No valid credential.", body = ErrorResponse),
        (status = 403, description = "The token lacks the evaluation write scope.", body = ErrorResponse),
        (status = 409, description = "The dataset key exists with different content.", body = EvaluationConflictResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn create_evaluation_dataset(
    State(state): State<AppState>,
    EvaluationWriteAccess(user): EvaluationWriteAccess,
    ApiJson(request): ApiJson<EvaluationDatasetCreate>,
) -> Result<Json<EvaluationDatasetRead>, ApiError> {
    let user_id = user.user_id.clone();
    let dataset = state
        .application_db
        .writer
        .call(move |connection| {
            repo::create_dataset(connection, &request, &user_id, UtcSeconds::now())
        })
        .await??;
    tracing::info!(
        audit = true,
        action = "create",
        resource_type = "evaluation_dataset",
        resource_id = %dataset.id,
        user_id = %user.user_id,
        user_email = %user.email,
        session_audit_id = %user.audit_id,
        application_key = %dataset.application_key,
        key = %dataset.key,
        "AUDIT: CREATE evaluation_dataset"
    );
    Ok(Json(dataset))
}

/// The page of a dataset listing to read.
#[derive(Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct ListDatasetsQuery {
    /// List only this application's datasets.
    #[param(value_type = Option<String>, min_length = 1, max_length = 128)]
    application_key: Option<KeyText>,
    /// The `next_cursor` of the previous page.
    #[param(value_type = Option<String>, min_length = 1, max_length = 1024)]
    cursor: Option<Cursor>,
    /// The most datasets to return.
    #[param(value_type = u32, minimum = 1, maximum = 100, default = 50)]
    #[serde(default)]
    limit: PageLimit,
}

/// List datasets, newest first.
#[utoipa::path(
    get,
    path = "/evaluation/datasets",
    operation_id = "list_evaluation_datasets",
    tag = "evaluation",
    params(ListDatasetsQuery),
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "One page of datasets.", body = EvaluationDatasetList),
        (status = 401, description = "No valid credential.", body = ErrorResponse),
        (status = 403, description = "The token lacks the evaluation read scope.", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn list_evaluation_datasets(
    State(state): State<AppState>,
    _access: EvaluationReadAccess,
    ApiQuery(query): ApiQuery<ListDatasetsQuery>,
) -> Result<Json<EvaluationDatasetList>, ApiError> {
    let after = query
        .cursor
        .as_ref()
        .map(|cursor| decode_time_cursor(DATASETS_CURSOR_KIND, cursor))
        .transpose()?;
    let limit = query.limit.get();
    let application_key = query.application_key;
    // One row past the page says whether another page follows.
    let mut items = state
        .application_db
        .reader
        .call(move |connection| {
            repo::list_datasets(
                connection,
                application_key.as_ref().map(|key| key.0.as_str()),
                after.as_ref(),
                limit + 1,
            )
        })
        .await?;
    let has_more = keep_page(&mut items, limit);
    let next_cursor = items.last().filter(|_| has_more).map(|last| {
        encode_time_cursor(
            DATASETS_CURSOR_KIND,
            &TimePosition {
                created_at: last.created_at,
                id: last.id.clone(),
            },
        )
    });
    Ok(Json(EvaluationDatasetList { items, next_cursor }))
}

/// Get one dataset with its cases in order.
#[utoipa::path(
    get,
    path = "/evaluation/datasets/{dataset_id}",
    operation_id = "get_evaluation_dataset",
    tag = "evaluation",
    params(("dataset_id" = String, Path, description = "The dataset's identifier.", min_length = 1, max_length = 64)),
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "The dataset and its cases.", body = EvaluationDatasetDetail),
        (status = 401, description = "No valid credential.", body = ErrorResponse),
        (status = 403, description = "The token lacks the evaluation read scope.", body = ErrorResponse),
        (status = 404, description = "Dataset not found", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn get_evaluation_dataset(
    State(state): State<AppState>,
    _access: EvaluationReadAccess,
    ApiPath(dataset_id): ApiPath<RecordId>,
) -> Result<Json<EvaluationDatasetDetail>, ApiError> {
    let detail = state
        .application_db
        .reader
        .call(move |connection| repo::get_dataset(connection, &dataset_id.0))
        .await?
        .ok_or(Refusal::NotFound("Dataset"))?;
    Ok(Json(detail))
}

/// Add a case to a draft dataset.
///
/// A repeated request returns the case it added.
#[utoipa::path(
    post,
    path = "/evaluation/datasets/{dataset_id}/cases",
    operation_id = "add_evaluation_case",
    tag = "evaluation",
    params(("dataset_id" = String, Path, description = "The dataset's identifier.", min_length = 1, max_length = 64)),
    request_body = EvaluationCaseCreate,
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "The case.", body = EvaluationCaseRead),
        (status = 401, description = "No valid credential.", body = ErrorResponse),
        (status = 403, description = "The token lacks the evaluation write scope.", body = ErrorResponse),
        (status = 404, description = "Dataset not found", body = ErrorResponse),
        (status = 409, description = "The case key exists with different content, or the dataset accepts no more cases.", body = EvaluationConflictResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn add_evaluation_case(
    State(state): State<AppState>,
    EvaluationWriteAccess(user): EvaluationWriteAccess,
    ApiPath(dataset_id): ApiPath<RecordId>,
    ApiJson(request): ApiJson<EvaluationCaseCreate>,
) -> Result<Json<EvaluationCaseRead>, ApiError> {
    request
        .validate_source_provenance()
        .map_err(ApiError::validation)?;
    let case = state
        .application_db
        .writer
        .call(move |connection| {
            repo::add_case(connection, &dataset_id.0, &request, UtcSeconds::now())
        })
        .await??;
    tracing::info!(
        audit = true,
        action = "create",
        resource_type = "evaluation_case",
        resource_id = %case.id,
        user_id = %user.user_id,
        user_email = %user.email,
        session_audit_id = %user.audit_id,
        dataset_id = %case.dataset_id,
        case_key = %case.case_key,
        "AUDIT: CREATE evaluation_case"
    );
    Ok(Json(case))
}

/// Lock a dataset so runs can start from it.
///
/// Locking cannot be undone.
#[utoipa::path(
    put,
    path = "/evaluation/datasets/{dataset_id}/lock",
    operation_id = "lock_evaluation_dataset",
    tag = "evaluation",
    params(("dataset_id" = String, Path, description = "The dataset's identifier.", min_length = 1, max_length = 64)),
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "The locked dataset.", body = EvaluationDatasetRead),
        (status = 401, description = "No valid credential.", body = ErrorResponse),
        (status = 403, description = "The token lacks the evaluation write scope.", body = ErrorResponse),
        (status = 404, description = "Dataset not found", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn lock_evaluation_dataset(
    State(state): State<AppState>,
    EvaluationWriteAccess(user): EvaluationWriteAccess,
    ApiPath(dataset_id): ApiPath<RecordId>,
) -> Result<Json<EvaluationDatasetRead>, ApiError> {
    let dataset = state
        .application_db
        .writer
        .call(move |connection| repo::lock_dataset(connection, &dataset_id.0, UtcSeconds::now()))
        .await??;
    tracing::info!(
        audit = true,
        action = "update",
        resource_type = "evaluation_dataset",
        resource_id = %dataset.id,
        user_id = %user.user_id,
        user_email = %user.email,
        session_audit_id = %user.audit_id,
        "AUDIT: UPDATE evaluation_dataset"
    );
    Ok(Json(dataset))
}

/// Start a run of a locked dataset.
///
/// A repeated request returns the run it started.
#[utoipa::path(
    post,
    path = "/evaluation/runs",
    operation_id = "start_evaluation_run",
    tag = "evaluation",
    request_body = EvaluationRunStart,
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "The run, with one attempt per case.", body = EvaluationRunDetail),
        (status = 401, description = "No valid credential.", body = ErrorResponse),
        (status = 403, description = "The token lacks the evaluation write scope.", body = ErrorResponse),
        (status = 404, description = "Dataset not found", body = ErrorResponse),
        (status = 409, description = "The request key exists with different content, or the dataset is not locked or has no case.", body = EvaluationConflictResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn start_evaluation_run(
    State(state): State<AppState>,
    EvaluationWriteAccess(user): EvaluationWriteAccess,
    ApiJson(request): ApiJson<EvaluationRunStart>,
) -> Result<Json<EvaluationRunDetail>, ApiError> {
    let user_id = user.user_id.clone();
    let detail = state
        .application_db
        .writer
        .call(move |connection| repo::start_run(connection, &request, &user_id, UtcSeconds::now()))
        .await??;
    tracing::info!(
        audit = true,
        action = "create",
        resource_type = "evaluation_run",
        resource_id = %detail.run.id,
        user_id = %user.user_id,
        user_email = %user.email,
        session_audit_id = %user.audit_id,
        dataset_id = %detail.run.dataset_id,
        request_key = %detail.run.request_key,
        run_label = %detail.run.run_label,
        "AUDIT: CREATE evaluation_run"
    );
    Ok(Json(detail))
}

/// The scope and page of a run listing to read.
#[derive(Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct ListRunsQuery {
    /// List only this dataset's runs.
    #[param(value_type = Option<String>, min_length = 1, max_length = 64)]
    dataset_id: Option<RecordId>,
    /// List only runs with a case of this target kind.
    #[param(inline)]
    target_kind: Option<TargetKind>,
    /// List only runs with a case of this target.
    #[param(value_type = Option<String>, min_length = 1, max_length = 128)]
    target_key: Option<KeyText>,
    /// List only runs with a case of this input version.
    #[param(value_type = Option<i64>, minimum = 1, maximum = 2147483647)]
    input_version: Option<Version>,
    /// List only runs with a case of this evaluation name.
    #[param(value_type = Option<String>, min_length = 1, max_length = 256)]
    evaluation_name: Option<NameText>,
    /// The `next_cursor` of the previous page.
    #[param(value_type = Option<String>, min_length = 1, max_length = 1024)]
    cursor: Option<Cursor>,
    /// The most runs to return.
    #[param(value_type = u32, minimum = 1, maximum = 100, default = 50)]
    #[serde(default)]
    limit: PageLimit,
}

/// List runs, newest first.
///
/// A run is listed when one case of its dataset matches every scope parameter
/// sent.
#[utoipa::path(
    get,
    path = "/evaluation/runs",
    operation_id = "list_evaluation_runs",
    tag = "evaluation",
    params(ListRunsQuery),
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "One page of runs.", body = EvaluationRunList),
        (status = 401, description = "No valid credential.", body = ErrorResponse),
        (status = 403, description = "The token lacks the evaluation read scope.", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn list_evaluation_runs(
    State(state): State<AppState>,
    _access: EvaluationReadAccess,
    ApiQuery(query): ApiQuery<ListRunsQuery>,
) -> Result<Json<EvaluationRunList>, ApiError> {
    let after = query
        .cursor
        .as_ref()
        .map(|cursor| decode_time_cursor(RUNS_CURSOR_KIND, cursor))
        .transpose()?;
    let limit = query.limit.get();
    let scope = EvaluationRunScope {
        dataset_id: query.dataset_id,
        target_kind: query.target_kind,
        target_key: query.target_key,
        input_version: query.input_version,
        evaluation_name: query.evaluation_name,
    };
    let listed_scope = scope.clone();
    // One row past the page says whether another page follows.
    let mut items = state
        .application_db
        .reader
        .call(move |connection| {
            repo::list_runs(connection, &listed_scope, after.as_ref(), limit + 1)
        })
        .await?;
    let has_more = keep_page(&mut items, limit);
    let next_cursor = items.last().filter(|_| has_more).map(|last| {
        encode_time_cursor(
            RUNS_CURSOR_KIND,
            &TimePosition {
                created_at: last.run.created_at,
                id: last.run.id.clone(),
            },
        )
    });
    Ok(Json(EvaluationRunList {
        scope,
        items,
        next_cursor,
    }))
}

/// Get one run with its dataset and every case's attempt.
#[utoipa::path(
    get,
    path = "/evaluation/runs/{run_id}",
    operation_id = "get_evaluation_run",
    tag = "evaluation",
    params(("run_id" = String, Path, description = "The run's identifier.", min_length = 1, max_length = 64)),
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "The run.", body = EvaluationRunDetail),
        (status = 401, description = "No valid credential.", body = ErrorResponse),
        (status = 403, description = "The token lacks the evaluation read scope.", body = ErrorResponse),
        (status = 404, description = "Run not found", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn get_evaluation_run(
    State(state): State<AppState>,
    _access: EvaluationReadAccess,
    ApiPath(run_id): ApiPath<RecordId>,
) -> Result<Json<EvaluationRunDetail>, ApiError> {
    let detail = state
        .application_db
        .reader
        .call(move |connection| repo::get_run(connection, &run_id.0))
        .await?
        .ok_or(Refusal::NotFound("Run"))?;
    Ok(Json(detail))
}

/// Get one attempt with its run, dataset, and case.
#[utoipa::path(
    get,
    path = "/evaluation/attempts/{attempt_id}",
    operation_id = "get_evaluation_attempt",
    tag = "evaluation",
    params(("attempt_id" = String, Path, description = "The attempt's identifier.", min_length = 1, max_length = 64)),
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "The attempt.", body = EvaluationAttemptDetail),
        (status = 401, description = "No valid credential.", body = ErrorResponse),
        (status = 403, description = "The token lacks the evaluation read scope.", body = ErrorResponse),
        (status = 404, description = "Attempt not found", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn get_evaluation_attempt(
    State(state): State<AppState>,
    _access: EvaluationReadAccess,
    ApiPath(attempt_id): ApiPath<RecordId>,
) -> Result<Json<EvaluationAttemptDetail>, ApiError> {
    let detail = state
        .application_db
        .reader
        .call(move |connection| repo::attempt_detail(connection, &attempt_id.0))
        .await?
        .ok_or(Refusal::NotFound("Attempt"))?;
    Ok(Json(detail))
}

/// Bind an attempt to the execution it evaluated.
///
/// A repeated request changes nothing.
#[utoipa::path(
    put,
    path = "/evaluation/attempts/{attempt_id}/evidence",
    operation_id = "bind_evaluation_attempt_evidence",
    tag = "evaluation",
    params(("attempt_id" = String, Path, description = "The attempt's identifier.", min_length = 1, max_length = 64)),
    request_body = EvaluationEvidenceBind,
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "The attempt with its evidence.", body = EvaluationAttemptRead),
        (status = 401, description = "No valid credential.", body = ErrorResponse),
        (status = 403, description = "The token lacks the evaluation write scope.", body = ErrorResponse),
        (status = 404, description = "Attempt not found", body = ErrorResponse),
        (status = 409, description = "The attempt has other evidence or a result, or the evidence belongs to another attempt.", body = EvaluationConflictResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn bind_evaluation_attempt_evidence(
    State(state): State<AppState>,
    EvaluationWriteAccess(user): EvaluationWriteAccess,
    ApiPath(attempt_id): ApiPath<RecordId>,
    ApiJson(request): ApiJson<EvaluationEvidenceBind>,
) -> Result<Json<EvaluationAttemptRead>, ApiError> {
    let attempt = state
        .application_db
        .writer
        .call(move |connection| {
            repo::bind_attempt_evidence(
                connection,
                &attempt_id.0,
                &request.evidence,
                UtcSeconds::now(),
            )
        })
        .await??;
    tracing::info!(
        audit = true,
        action = "update",
        resource_type = "evaluation_attempt",
        resource_id = %attempt.id,
        user_id = %user.user_id,
        user_email = %user.email,
        session_audit_id = %user.audit_id,
        "AUDIT: UPDATE evaluation_attempt"
    );
    Ok(Json(attempt))
}

/// Record an attempt's result.
///
/// The last result of a run completes the run. A repeated request changes
/// nothing.
#[utoipa::path(
    put,
    path = "/evaluation/attempts/{attempt_id}/result",
    operation_id = "record_evaluation_attempt_result",
    tag = "evaluation",
    params(("attempt_id" = String, Path, description = "The attempt's identifier.", min_length = 1, max_length = 64)),
    request_body = EvaluationAttemptResult,
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "The attempt with its result.", body = EvaluationAttemptRead),
        (status = 401, description = "No valid credential.", body = ErrorResponse),
        (status = 403, description = "The token lacks the evaluation write scope.", body = ErrorResponse),
        (status = 404, description = "Attempt not found", body = ErrorResponse),
        (status = 409, description = "The attempt has another result, or a judgment has no evidence.", body = EvaluationConflictResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn record_evaluation_attempt_result(
    State(state): State<AppState>,
    EvaluationWriteAccess(user): EvaluationWriteAccess,
    ApiPath(attempt_id): ApiPath<RecordId>,
    ApiJson(request): ApiJson<EvaluationAttemptResult>,
) -> Result<Json<EvaluationAttemptRead>, ApiError> {
    let attempt = state
        .application_db
        .writer
        .call(move |connection| {
            repo::record_attempt_result(connection, &attempt_id.0, &request, UtcSeconds::now())
        })
        .await??;
    tracing::info!(
        audit = true,
        action = "update",
        resource_type = "evaluation_attempt",
        resource_id = %attempt.id,
        user_id = %user.user_id,
        user_email = %user.email,
        session_audit_id = %user.audit_id,
        "AUDIT: UPDATE evaluation_attempt"
    );
    Ok(Json(attempt))
}

/// The evidence reference to look up, and the page of the listing to read.
#[derive(Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct EvidenceMembershipQuery {
    /// Which kind of reference the other parameters describe.
    #[param(inline)]
    kind: EvidenceKind,
    /// Exact service.namespace; empty is explicit
    #[param(value_type = String, max_length = 256)]
    service_namespace: ServiceNamespaceText,
    /// Exact service.name
    #[param(value_type = String, min_length = 1, max_length = 256)]
    service_name: ExecutionIdentityText,
    /// Sent with `junjo_execution` only.
    #[param(inline)]
    executable_type: Option<ExecutableType>,
    /// Sent with `junjo_execution` only.
    #[param(value_type = Option<String>, min_length = 1, max_length = 256)]
    runtime_id: Option<ExecutionIdentityText>,
    /// Sent with `otel_span` only.
    #[param(value_type = Option<String>, pattern = "^[0-9a-f]{32}$")]
    trace_id: Option<TraceId>,
    /// Sent with `otel_span` only.
    #[param(value_type = Option<String>, pattern = "^[0-9a-f]{16}$")]
    span_id: Option<SpanId>,
    /// The `next_cursor` of the previous page.
    #[param(value_type = Option<String>, min_length = 1, max_length = 1024)]
    cursor: Option<Cursor>,
    /// The most records to return.
    #[param(value_type = u32, minimum = 1, maximum = 100, default = 50)]
    #[serde(default)]
    limit: PageLimit,
}

impl EvidenceMembershipQuery {
    /// The reference these parameters name. Each kind takes exactly its own
    /// identity parameters.
    fn evidence(&self) -> Result<ExecutionEvidenceReference, ApiError> {
        match (
            self.kind,
            &self.executable_type,
            &self.runtime_id,
            &self.trace_id,
            &self.span_id,
        ) {
            (EvidenceKind::JunjoExecution, Some(executable_type), Some(runtime_id), None, None) => {
                Ok(ExecutionEvidenceReference::JunjoExecution(
                    SemanticExecutionReference {
                        kind: SemanticExecutionKind::JunjoExecution,
                        service_namespace: self.service_namespace.clone(),
                        service_name: self.service_name.clone(),
                        executable_type: *executable_type,
                        runtime_id: runtime_id.clone(),
                    },
                ))
            }
            (EvidenceKind::JunjoExecution, ..) => Err(ApiError::validation(
                "Invalid junjo_execution evidence identity",
            )),
            (EvidenceKind::OtelSpan, None, None, Some(trace_id), Some(span_id)) => Ok(
                ExecutionEvidenceReference::OtelSpan(OpenTelemetrySpanReference {
                    kind: OpenTelemetrySpanKind::OtelSpan,
                    service_namespace: self.service_namespace.clone(),
                    service_name: self.service_name.clone(),
                    trace_id: trace_id.clone(),
                    span_id: span_id.clone(),
                }),
            ),
            (EvidenceKind::OtelSpan, ..) => {
                Err(ApiError::validation("Invalid otel_span evidence identity"))
            }
        }
    }
}

/// Find the records that use one execution's evidence.
///
/// The attempt it is the subject of comes first, then the cases generated
/// from it.
#[utoipa::path(
    get,
    path = "/evaluation/evidence-membership",
    operation_id = "find_evaluation_evidence_membership",
    tag = "evaluation",
    params(EvidenceMembershipQuery),
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "One page of records.", body = EvaluationEvidenceMembershipList),
        (status = 401, description = "No valid credential.", body = ErrorResponse),
        (status = 403, description = "The token lacks the evaluation read scope.", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn find_evaluation_evidence_membership(
    State(state): State<AppState>,
    _access: EvaluationReadAccess,
    ApiQuery(query): ApiQuery<EvidenceMembershipQuery>,
) -> Result<Json<EvaluationEvidenceMembershipList>, ApiError> {
    let evidence = query.evidence()?;
    let after = query
        .cursor
        .as_ref()
        .map(decode_membership_cursor)
        .transpose()?;
    let limit = query.limit.get();
    // One row past the page says whether another page follows.
    let mut items = state
        .application_db
        .reader
        .call(move |connection| {
            repo::find_evidence_membership(connection, &evidence, after.as_ref(), limit + 1)
        })
        .await?;
    let has_more = keep_page(&mut items, limit);
    let next_cursor = items.last().filter(|_| has_more).map(|last| {
        // An attempt subject is placed by its attempt, a case source by its
        // case.
        let record_id = last.attempt_id.as_ref().unwrap_or(&last.case_id);
        encode_membership_cursor(&MembershipPosition {
            role: last.role,
            record_id: record_id.clone(),
        })
    });
    Ok(Json(EvaluationEvidenceMembershipList {
        items,
        next_cursor,
    }))
}

#[cfg(test)]
mod tests;
