//! Agent execution queries.
//!
//! Span selection is physical: it finds a service's Agent spans. Everything
//! that makes a span an Agent execution, and every filter, is decided here
//! from the evidence the span carries.

use axum::Json;
use axum::extract::State;
use junjo_evidence::agent_diagnostics::assembler::assemble_agent_summary;
use junjo_evidence::agent_diagnostics::schemas::{
    AgentEvidenceError, AgentExecutionSummary, Outcome,
};
use junjo_evidence::json::get;
use junjo_evidence::timestamps::{Timestamp, TimestampError};
use junjo_evidence::trace_evidence::schemas::NormalizedSpanEvidence;
use serde::Deserialize;
use utoipa::IntoParams;
use utoipa_axum::router::OpenApiRouter;
use utoipa_axum::routes;

use crate::error::{ApiError, ApiQuery, ErrorResponse};
use crate::features::auth::AuthenticatedUser;
use crate::features::otel_spans::query::Span;
use crate::features::otel_spans::repository;
use crate::pagination::Limit;
use crate::state::AppState;
use crate::text::NonEmptyText;

/// An instant a caller sends as a time bound. It must carry an offset.
#[derive(Debug, Clone, Copy, Deserialize)]
#[serde(try_from = "String")]
pub struct TimeBound(Timestamp);

impl TryFrom<String> for TimeBound {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        Timestamp::parse(&value)
            .map(Self)
            .map_err(|error| match error {
                TimestampError::MissingOffset => "time must include an offset".to_string(),
                TimestampError::Invalid => "time must be an ISO 8601 date and time".to_string(),
            })
    }
}

/// The service to list and the filters to apply.
#[derive(Debug, Deserialize, IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in = Query)]
pub struct AgentExecutionListQuery {
    /// Exact service.namespace; empty is explicit
    service_namespace: String,
    /// Exact service.name
    #[param(value_type = String, min_length = 1)]
    service_name: NonEmptyText,
    #[param(value_type = Option<String>, min_length = 1)]
    agent_key: Option<NonEmptyText>,
    #[param(value_type = Option<String>, min_length = 1)]
    structural_id: Option<NonEmptyText>,
    #[param(value_type = Option<String>, min_length = 1)]
    service_version: Option<NonEmptyText>,
    #[param(inline)]
    outcome: Option<Outcome>,
    /// Only executions that started at or after this instant.
    #[param(value_type = Option<String>, format = DateTime)]
    start_time: Option<TimeBound>,
    /// Only executions that ended at or before this instant.
    #[param(value_type = Option<String>, format = DateTime)]
    end_time: Option<TimeBound>,
    /// The most executions to return.
    #[param(value_type = u32, minimum = 1, maximum = 250, default = 100)]
    #[serde(default)]
    limit: Limit<250, 100>,
}

/// Evidence that cannot be read as an Agent execution is a conflict with the
/// stored evidence, never a caller validation error.
impl From<AgentEvidenceError> for ApiError {
    fn from(error: AgentEvidenceError) -> Self {
        let diagnostics = serde_json::to_value(&error.diagnostics).unwrap_or_default();
        ApiError::conflict(error.code.as_str(), error.message)
            .with_extra("diagnostics", diagnostics)
    }
}

/// This feature's routes, relative to `/api/v1`.
pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new().routes(routes!(list_agent_executions))
}

/// List the Agent executions of one service, newest first.
#[utoipa::path(
    get,
    path = "/agent-executions",
    operation_id = "list_agent_executions",
    tag = "agent-executions",
    params(AgentExecutionListQuery),
    responses(
        (status = 200, description = "The matching Agent executions.", body = Vec<AgentExecutionSummary>),
        (status = 401, description = "No signed-in user.", body = ErrorResponse),
        (status = 409, description = "Stored evidence cannot be read as an Agent execution.", body = AgentEvidenceError),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn list_agent_executions(
    State(state): State<AppState>,
    _user: AuthenticatedUser,
    ApiQuery(query): ApiQuery<AgentExecutionListQuery>,
) -> Result<Json<Vec<AgentExecutionSummary>>, ApiError> {
    if let (Some(start), Some(end)) = (query.start_time, query.end_time)
        && start.0 > end.0
    {
        return Err(ApiError::validation(
            "start_time must be earlier than or equal to end_time",
        ));
    }
    let owner_spans: Vec<NormalizedSpanEvidence> =
        repository::agent_spans(&state, query.service_name.as_str())
            .await?
            .iter()
            .map(Span::to_evidence)
            .collect();
    Ok(Json(summaries(&owner_spans, &query)?))
}

/// The summaries of the owner spans that are in the queried service and pass
/// every filter, newest first, up to the limit.
fn summaries(
    owner_spans: &[NormalizedSpanEvidence],
    query: &AgentExecutionListQuery,
) -> Result<Vec<AgentExecutionSummary>, AgentEvidenceError> {
    let matches = |wanted: &Option<NonEmptyText>, actual: Option<&str>| {
        wanted
            .as_ref()
            .is_none_or(|wanted| Some(wanted.as_str()) == actual)
    };
    let mut selected = Vec::new();
    for owner_span in owner_spans {
        if !in_service(owner_span, query) {
            continue;
        }
        let summary = assemble_agent_summary(&owner_span.to_object())?;
        if summary.service.namespace == query.service_namespace
            && summary.service.name == query.service_name.as_str()
            && matches(&query.agent_key, Some(&summary.agent_key))
            && matches(&query.structural_id, Some(&summary.structural_id))
            && matches(&query.service_version, summary.service.version.as_deref())
            && query
                .outcome
                .is_none_or(|outcome| outcome == summary.outcome)
            && query
                .start_time
                .is_none_or(|start| summary.start_time >= start.0)
            && query.end_time.is_none_or(|end| summary.end_time <= end.0)
        {
            selected.push(summary);
        }
    }
    // Stable: executions that started together keep their selection order.
    selected.sort_by_key(|summary| std::cmp::Reverse(summary.start_time));
    selected.truncate(query.limit.get() as usize);
    Ok(selected)
}

/// Whether a span's resource names exactly the queried service. A span of
/// another service is skipped before its evidence is read, so it can never
/// fail this service's listing.
fn in_service(span: &NormalizedSpanEvidence, query: &AgentExecutionListQuery) -> bool {
    let resource = &span.resource_attributes_json;
    // A service without a namespace has the empty namespace.
    let namespace = match resource.get("service.namespace") {
        None => Some(""),
        Some(value) => value.as_str(),
    };
    get(resource, "service.name").as_str() == Some(query.service_name.as_str())
        && namespace == Some(query.service_namespace.as_str())
}

#[cfg(test)]
mod tests;
