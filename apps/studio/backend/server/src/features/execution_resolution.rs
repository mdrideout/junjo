//! Exact execution identity resolution.
//!
//! An executable's service, type, and runtime identity resolve to the one
//! owner span that records it, and to the Studio pages that show it. Two
//! owner spans with one identity are a conflict: nothing is selected.

use std::collections::{HashMap, HashSet};

use axum::Json;
use axum::extract::State;
use junjo_evidence::json::{Json as JsonValue, get};
use junjo_evidence::telemetry_contract::{is_active_contract_version, nonempty_text};
use junjo_evidence::trace_evidence::assembler::{percent_encode, span_path};
use junjo_evidence::trace_evidence::schemas::NormalizedSpanEvidence;
use serde::{Deserialize, Serialize};
use utoipa::{IntoParams, ToSchema};
use utoipa_axum::router::OpenApiRouter;
use utoipa_axum::routes;

use crate::error::{ApiError, ApiQuery, ErrorResponse};
use crate::features::evaluation_tokens::access::EvidenceReadAccess;
use crate::features::otel_spans::query::Span;
use crate::features::otel_spans::repository;
use crate::state::AppState;
use crate::text::NonEmptyText;

const AMBIGUOUS_EXECUTION_IDENTITY: &str = "ambiguous_execution_identity";

/// The kinds of executable that own an execution.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum ExecutableType {
    Workflow,
    Subflow,
    Agent,
}

impl ExecutableType {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Workflow => "workflow",
            Self::Subflow => "subflow",
            Self::Agent => "agent",
        }
    }
}

/// The exact identity of one execution.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExecutionIdentity {
    /// The exact `service.namespace`. Empty means the service has none.
    pub service_namespace: String,
    pub service_name: String,
    pub executable_type: ExecutableType,
    pub runtime_id: String,
}

/// The identity to resolve.
#[derive(Debug, Deserialize, IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in = Query)]
pub struct ExecutionResolutionQuery {
    /// Exact service.namespace; empty is explicit
    service_namespace: String,
    /// Exact service.name
    #[param(value_type = String, min_length = 1)]
    service_name: NonEmptyText,
    #[param(inline)]
    executable_type: ExecutableType,
    #[param(value_type = String, min_length = 1)]
    runtime_id: NonEmptyText,
}

/// One resolved execution: its owner span and the Studio pages that show it.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ExecutionResolution {
    pub service_namespace: String,
    #[schema(min_length = 1)]
    pub service_name: String,
    #[schema(inline)]
    pub executable_type: ExecutableType,
    #[schema(min_length = 1)]
    pub runtime_id: String,
    #[schema(pattern = "^[0-9a-f]{32}$")]
    pub trace_id: String,
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub span_id: String,
    /// The page that shows the execution.
    #[schema(pattern = "^/")]
    pub detail_path: String,
    /// The page that shows where the execution failed.
    #[schema(pattern = "^/")]
    pub failure_path: String,
    /// The page that shows the execution's trace.
    #[schema(pattern = "^/")]
    pub trace_path: String,
}

/// The body of the conflict response when an identity matches more than one
/// owner span. It describes what `ambiguous` builds and is never constructed.
#[allow(dead_code)]
#[derive(Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ExecutionResolutionConflictResponse {
    #[schema(inline)]
    code: AmbiguousExecutionIdentity,
    #[schema(min_length = 1)]
    message: String,
    #[schema(minimum = 2)]
    match_count: usize,
}

#[allow(dead_code)]
#[derive(Serialize, ToSchema)]
enum AmbiguousExecutionIdentity {
    #[serde(rename = "ambiguous_execution_identity")]
    AmbiguousExecutionIdentity,
}

fn ambiguous(match_count: usize) -> ApiError {
    ApiError::conflict(
        AMBIGUOUS_EXECUTION_IDENTITY,
        "Execution identity resolved to multiple owner spans.",
    )
    .with_extra("match_count", match_count)
}

/// This feature's routes, relative to `/api/v1`.
pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new().routes(routes!(resolve_execution))
}

/// Resolve one execution identity to its owner span.
#[utoipa::path(
    get,
    path = "/execution-resolution",
    operation_id = "resolve_execution",
    tag = "execution-resolution",
    params(ExecutionResolutionQuery),
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "The resolved execution.", body = ExecutionResolution),
        (status = 401, description = "No valid credential.", body = ErrorResponse),
        (status = 403, description = "The token lacks the evidence scope.", body = ErrorResponse),
        (status = 404, description = "Execution owner span not found", body = ErrorResponse),
        (status = 409, description = "More than one owner span records this execution.", body = ExecutionResolutionConflictResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn resolve_execution(
    State(state): State<AppState>,
    _access: EvidenceReadAccess,
    ApiQuery(query): ApiQuery<ExecutionResolutionQuery>,
) -> Result<Json<ExecutionResolution>, ApiError> {
    let identity = ExecutionIdentity {
        service_namespace: query.service_namespace,
        service_name: query.service_name.into_string(),
        executable_type: query.executable_type,
        runtime_id: query.runtime_id.into_string(),
    };
    resolve(&state, &identity)
        .await?
        .map(Json)
        .ok_or_else(|| ApiError::not_found("Execution not found"))
}

/// Resolve one identity. `None` means no owner span records it; more than
/// one is the conflict error.
pub async fn resolve(
    state: &AppState,
    identity: &ExecutionIdentity,
) -> Result<Option<ExecutionResolution>, ApiError> {
    let candidates: Vec<NormalizedSpanEvidence> = repository::executable_spans(
        state,
        &identity.service_name,
        identity.executable_type.as_str(),
        &identity.runtime_id,
    )
    .await?
    .iter()
    .map(Span::to_evidence)
    .collect();
    let owner = match owners(&candidates, identity).as_slice() {
        [] => return Ok(None),
        [owner] => *owner,
        several => return Err(ambiguous(several.len())),
    };

    let (selected_node, failed_node) = if identity.executable_type == ExecutableType::Agent {
        (None, None)
    } else {
        let node_runtime_id = single_graph_node_runtime_id(owner);
        let owner_failed = has_failure_signal(owner);
        if node_runtime_id.is_none() && !owner_failed {
            (None, None)
        } else {
            let trace: Vec<NormalizedSpanEvidence> =
                repository::trace_spans(state, &owner.trace_id)
                    .await?
                    .iter()
                    .map(Span::to_evidence)
                    .collect();
            (
                node_runtime_id
                    .and_then(|runtime_id| single_graph_node_span_id(owner, &runtime_id, &trace)),
                owner_failed
                    .then(|| single_failed_node_span_id(owner, &trace))
                    .flatten(),
            )
        }
    };
    Ok(Some(resolution(
        identity,
        owner,
        selected_node,
        failed_node,
    )))
}

/// The candidates that are exactly this execution's owner span under the
/// active telemetry contract.
fn owners<'a>(
    candidates: &'a [NormalizedSpanEvidence],
    identity: &ExecutionIdentity,
) -> Vec<&'a NormalizedSpanEvidence> {
    candidates
        .iter()
        .filter(|span| {
            let attributes = &span.attributes_json;
            let resource = &span.resource_attributes_json;
            // A service without a namespace has the empty namespace.
            let namespace = match resource.get("service.namespace") {
                None => Some(""),
                Some(value) => value.as_str(),
            };
            is_active_contract_version(get(attributes, "junjo.telemetry.contract_version"))
                && get(attributes, "junjo.span_type").as_str()
                    == Some(identity.executable_type.as_str())
                && get(attributes, "junjo.executable_runtime_id").as_str()
                    == Some(identity.runtime_id.as_str())
                && get(resource, "service.name").as_str() == Some(identity.service_name.as_str())
                && namespace == Some(identity.service_namespace.as_str())
        })
        .collect()
}

fn resolution(
    identity: &ExecutionIdentity,
    owner: &NormalizedSpanEvidence,
    selected_node: Option<String>,
    failed_node: Option<String>,
) -> ExecutionResolution {
    let (trace_id, span_id) = (&owner.trace_id, &owner.span_id);
    let (detail_path, failure_path) = if identity.executable_type == ExecutableType::Agent {
        let agent = format!("/agents/{trace_id}/{span_id}");
        (agent.clone(), agent)
    } else {
        let workflow = format!(
            "/workflows/{}/{trace_id}/{span_id}",
            percent_encode(&identity.service_name)
        );
        let with_node = |node: Option<String>| match node {
            Some(node) => format!("{workflow}/{node}"),
            None => workflow.clone(),
        };
        (with_node(selected_node), with_node(failed_node))
    };
    ExecutionResolution {
        service_namespace: identity.service_namespace.clone(),
        service_name: identity.service_name.clone(),
        executable_type: identity.executable_type,
        runtime_id: identity.runtime_id.clone(),
        trace_id: trace_id.clone(),
        span_id: span_id.clone(),
        detail_path,
        failure_path,
        trace_path: span_path(&identity.service_name, trace_id, span_id),
    }
}

/// The runtime identity of the one Node in a one-Node Workflow graph.
fn single_graph_node_runtime_id(owner: &NormalizedSpanEvidence) -> Option<String> {
    let snapshot = get(
        &owner.attributes_json,
        "junjo.workflow.execution_graph_snapshot",
    );
    let parsed;
    let snapshot = match snapshot {
        JsonValue::String(text) => {
            parsed = serde_json::from_str::<JsonValue>(text).ok()?;
            &parsed
        }
        other => other,
    };
    let [node] = snapshot.as_object()?.get("nodes")?.as_array()?.as_slice() else {
        return None;
    };
    nonempty_text(node.as_object()?.get("nodeRuntimeId")?).map(str::to_string)
}

fn is_node(span: &NormalizedSpanEvidence) -> bool {
    is_active_contract_version(get(
        &span.attributes_json,
        "junjo.telemetry.contract_version",
    )) && get(&span.attributes_json, "junjo.span_type").as_str() == Some("node")
}

/// The span of the one real Node in a one-Node Workflow. The Node is found by
/// its runtime identity, never by its name.
fn single_graph_node_span_id(
    owner: &NormalizedSpanEvidence,
    node_runtime_id: &str,
    trace: &[NormalizedSpanEvidence],
) -> Option<String> {
    let mut nodes = trace.iter().filter(|span| {
        span.trace_id == owner.trace_id
            && span.parent_span_id.as_deref() == Some(owner.span_id.as_str())
            && is_node(span)
            && get(&span.attributes_json, "junjo.executable_runtime_id").as_str()
                == Some(node_runtime_id)
    });
    match (nodes.next(), nodes.next()) {
        (Some(node), None) => Some(node.span_id.clone()),
        _ => None,
    }
}

/// The span of the one failed Node inside a failed Workflow.
fn single_failed_node_span_id(
    owner: &NormalizedSpanEvidence,
    trace: &[NormalizedSpanEvidence],
) -> Option<String> {
    let parents: HashMap<&str, Option<&str>> = trace
        .iter()
        .map(|span| (span.span_id.as_str(), span.parent_span_id.as_deref()))
        .collect();
    let mut failed = trace.iter().filter(|span| {
        is_node(span) && has_failure_signal(span) && is_descendant(span, &owner.span_id, &parents)
    });
    match (failed.next(), failed.next()) {
        (Some(node), None) => Some(node.span_id.clone()),
        _ => None,
    }
}

/// Whether a span records a failure: an error type, or an exception or
/// hook-error event.
fn has_failure_signal(span: &NormalizedSpanEvidence) -> bool {
    nonempty_text(get(&span.attributes_json, "error.type")).is_some()
        || span.events_json.iter().any(|event| {
            matches!(
                event.get("name").and_then(JsonValue::as_str),
                Some("exception" | "junjo.hook_error")
            )
        })
}

fn is_descendant(
    span: &NormalizedSpanEvidence,
    ancestor_span_id: &str,
    parents: &HashMap<&str, Option<&str>>,
) -> bool {
    let mut visited = HashSet::new();
    let mut parent = span.parent_span_id.as_deref();
    while let Some(parent_span_id) = parent {
        if parent_span_id == ancestor_span_id {
            return true;
        }
        // A parent cycle in malformed evidence ends the walk.
        if !visited.insert(parent_span_id) {
            return false;
        }
        match parents.get(parent_span_id) {
            Some(next) => parent = *next,
            None => return false,
        }
    }
    false
}

#[cfg(test)]
mod tests;
