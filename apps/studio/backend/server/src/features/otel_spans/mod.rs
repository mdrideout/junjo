//! Raw observability API over the two span tiers.
//!
//! Query flow (ingestion ADR-002):
//! 1. Ask ingestion for the hot snapshot and its recent-cold bridge.
//! 2. Select indexed cold files from the metadata index.
//! 3. Read cold, recent-cold, and hot data together with DataFusion.

use axum::Json;
use axum::extract::State;
use serde::Deserialize;
use utoipa::IntoParams;
use utoipa_axum::router::OpenApiRouter;
use utoipa_axum::routes;

use crate::error::{ApiError, ApiPath, ApiQuery, ErrorResponse};
use crate::features::auth::AuthenticatedUser;
use crate::pagination::Limit;
use crate::state::AppState;

pub mod query;
pub mod repository;

use query::Span;

/// Upper bound on recent cold files added to one query. Recent files are not
/// in the metadata index yet, so they cannot be narrowed by trace or service.
const MAX_RECENT_COLD_FILES_PER_QUERY: usize = 20;
const MAX_RECENT_COLD_FILES_FOR_SERVICE_DISCOVERY: usize = 5;

/// Put a bounded list of recent cold files ahead of the indexed ones, without
/// duplicates. Ingestion is the source of truth for what is recent.
fn augment_with_recent_cold_files(
    file_paths: Vec<String>,
    recent_cold_paths: &[String],
    limit: usize,
) -> Vec<String> {
    let recent: Vec<String> = recent_cold_paths.iter().take(limit).cloned().collect();
    if recent.is_empty() {
        return file_paths;
    }
    let mut combined = recent.clone();
    combined.extend(file_paths.into_iter().filter(|path| !recent.contains(path)));
    combined
}

/// The most spans one listing returns.
type SpanLimit = Limit<250, 100>;

/// This feature's routes, relative to `/api/v1`.
///
/// A service name is one path segment. A name that contains `/` is sent
/// percent-encoded, as every Studio client sends it.
pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(list_services))
        .routes(routes!(get_service_spans))
        .routes(routes!(get_root_spans))
        .routes(routes!(get_workflow_spans))
        .routes(routes!(get_trace_spans))
        .routes(routes!(get_span))
}

/// List all distinct service names, alphabetically.
#[utoipa::path(
    get,
    path = "/observability/services",
    operation_id = "list_services_api_v1_observability_services_get",
    tag = "observability",
    responses(
        (status = 200, description = "Every service that has stored spans.", body = Vec<String>),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
    )
)]
pub async fn list_services(
    State(state): State<AppState>,
    _user: AuthenticatedUser,
) -> Result<Json<Vec<String>>, ApiError> {
    Ok(Json(repository::distinct_service_names(&state).await?))
}

/// How many spans a listing returns.
#[derive(Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct SpanListQuery {
    /// Maximum spans to return
    #[param(value_type = u32, minimum = 1, maximum = 250, default = 100)]
    #[serde(default)]
    limit: SpanLimit,
}

/// Get the newest spans of a service.
#[utoipa::path(
    get,
    path = "/observability/services/{service_name}/spans",
    operation_id = "get_service_spans_api_v1_observability_services__service_name__spans_get",
    tag = "observability",
    params(("service_name" = String, Path, description = "The service's name."), SpanListQuery),
    responses(
        (status = 200, description = "Spans, newest first.", body = Vec<Object>),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn get_service_spans(
    State(state): State<AppState>,
    _user: AuthenticatedUser,
    ApiPath(service_name): ApiPath<String>,
    ApiQuery(query): ApiQuery<SpanListQuery>,
) -> Result<Json<Vec<Span>>, ApiError> {
    let limit = query.limit.get() as usize;
    Ok(Json(
        repository::service_spans(&state, &service_name, limit).await?,
    ))
}

/// Which root spans a listing returns.
#[derive(Deserialize, IntoParams)]
#[into_params(parameter_in = Query)]
pub struct RootSpanListQuery {
    /// Filter for traces containing LLM operations
    #[param(default = false)]
    #[serde(default)]
    has_llm: bool,
    /// Maximum spans to return
    #[param(value_type = u32, minimum = 1, maximum = 250, default = 100)]
    #[serde(default)]
    limit: SpanLimit,
}

/// Get the newest root spans of a service. A root span has no parent: it is
/// the entry point of a trace.
#[utoipa::path(
    get,
    path = "/observability/services/{service_name}/spans/root",
    operation_id = "get_root_spans_api_v1_observability_services__service_name__spans_root_get",
    tag = "observability",
    params(("service_name" = String, Path, description = "The service's name."), RootSpanListQuery),
    responses(
        (status = 200, description = "Root spans, newest first.", body = Vec<Object>),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn get_root_spans(
    State(state): State<AppState>,
    _user: AuthenticatedUser,
    ApiPath(service_name): ApiPath<String>,
    ApiQuery(query): ApiQuery<RootSpanListQuery>,
) -> Result<Json<Vec<Span>>, ApiError> {
    let limit = query.limit.get() as usize;
    let spans = if query.has_llm {
        repository::root_spans_with_llm(&state, &service_name, limit).await?
    } else {
        repository::root_spans(&state, &service_name, limit).await?
    };
    Ok(Json(spans))
}

/// Get the newest Workflow spans of a service.
#[utoipa::path(
    get,
    path = "/observability/services/{service_name}/workflows",
    operation_id = "get_workflow_spans_api_v1_observability_services__service_name__workflows_get",
    tag = "observability",
    params(("service_name" = String, Path, description = "The service's name."), SpanListQuery),
    responses(
        (status = 200, description = "Workflow spans, newest first.", body = Vec<Object>),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn get_workflow_spans(
    State(state): State<AppState>,
    _user: AuthenticatedUser,
    ApiPath(service_name): ApiPath<String>,
    ApiQuery(query): ApiQuery<SpanListQuery>,
) -> Result<Json<Vec<Span>>, ApiError> {
    let limit = query.limit.get() as usize;
    Ok(Json(
        repository::workflow_spans(&state, &service_name, limit).await?,
    ))
}

/// Get every span of a trace, newest first.
#[utoipa::path(
    get,
    path = "/observability/traces/{trace_id}/spans",
    operation_id = "get_trace_spans_api_v1_observability_traces__trace_id__spans_get",
    tag = "observability",
    params(("trace_id" = String, Path, description = "The trace's identifier.")),
    responses(
        (status = 200, description = "The trace's spans, newest first.", body = Vec<Object>),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
    )
)]
pub async fn get_trace_spans(
    State(state): State<AppState>,
    _user: AuthenticatedUser,
    ApiPath(trace_id): ApiPath<String>,
) -> Result<Json<Vec<Span>>, ApiError> {
    Ok(Json(repository::trace_spans(&state, &trace_id).await?))
}

/// Get one span of a trace. The body is null when the trace has no such
/// span.
#[utoipa::path(
    get,
    path = "/observability/traces/{trace_id}/spans/{span_id}",
    operation_id = "get_span_api_v1_observability_traces__trace_id__spans__span_id__get",
    tag = "observability",
    params(
        ("trace_id" = String, Path, description = "The trace's identifier."),
        ("span_id" = String, Path, description = "The span's identifier."),
    ),
    responses(
        (status = 200, description = "The span, or null.", body = Option<Object>),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
    )
)]
pub async fn get_span(
    State(state): State<AppState>,
    _user: AuthenticatedUser,
    ApiPath((trace_id, span_id)): ApiPath<(String, String)>,
) -> Result<Json<Option<Span>>, ApiError> {
    Ok(Json(repository::span(&state, &trace_id, &span_id).await?))
}

#[cfg(test)]
mod route_tests;

#[cfg(test)]
mod tests {
    use super::*;

    fn paths(names: &[&str]) -> Vec<String> {
        names.iter().map(|name| name.to_string()).collect()
    }

    #[test]
    fn recent_cold_files_come_first_without_duplicates() {
        let combined = augment_with_recent_cold_files(
            paths(&["a", "b", "c"]),
            &paths(&["c", "d"]),
            MAX_RECENT_COLD_FILES_PER_QUERY,
        );
        assert_eq!(combined, paths(&["c", "d", "a", "b"]));
    }

    #[test]
    fn recent_cold_files_are_bounded() {
        let combined = augment_with_recent_cold_files(paths(&["a"]), &paths(&["x", "y", "z"]), 2);
        assert_eq!(combined, paths(&["x", "y", "a"]));
        assert_eq!(
            augment_with_recent_cold_files(paths(&["a"]), &[], 2),
            paths(&["a"])
        );
    }
}
