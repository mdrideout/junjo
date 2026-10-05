//! Cohesive trace evidence: one trace's complete spans with the verified
//! annotations Studio derives from them.
//!
//! An evaluation Attempt names the execution it evaluated. The Attempt routes
//! resolve that name to stored evidence: a payload-light manifest of the
//! execution's whole trace, and complete evidence for the spans a caller
//! selects from it.

use axum::Json;
use axum::extract::State;
use indexmap::IndexMap;
use junjo_evidence::json::get;
use junjo_evidence::trace_evidence::assembler::{
    assemble_attempt_evidence_manifest, assemble_trace_evidence, select_attempt_span_evidence,
    span_path,
};
use junjo_evidence::trace_evidence::schemas::{
    ExecutableManifestEntry, ExecutableRelationships, FailureSpanManifestEntry,
    NormalizedSpanEvidence, OperationManifestEntry, SelectedSpanEvidence, SpanManifestEntry,
    StoreManifestEntry, TraceEvidence, TraceEvidenceDiagnostic, TraceManifestSummary,
};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use utoipa_axum::router::OpenApiRouter;
use utoipa_axum::routes;

use crate::error::{ApiError, ApiJson, ApiPath, ErrorResponse};
use crate::features::evaluation::schemas::{SpanId, TraceId};
use crate::features::evaluation::{self, ExecutionEvidenceReference, RecordId};
use crate::features::evaluation_tokens::access::EvidenceReadAccess;
use crate::features::execution_resolution::{
    self, ExecutionIdentity, ExecutionResolutionConflictResponse,
};
use crate::features::otel_spans::query::Span;
use crate::features::otel_spans::repository;
use crate::state::AppState;

/// One bound evaluation subject resolved to exact stored evidence.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AttemptEvidenceSubject {
    #[schema(min_length = 1, max_length = 64)]
    pub attempt_id: String,
    // A description here would wrap the inlined union in `allOf`.
    #[schema(inline)]
    pub reference: ExecutionEvidenceReference,
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

/// Trace-aware middle layer between an Attempt and complete evidence.
#[derive(Debug, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AttemptEvidenceManifest {
    pub subject: AttemptEvidenceSubject,
    pub trace: TraceManifestSummary,
    pub spans: Vec<SpanManifestEntry>,
    pub failures: Vec<FailureSpanManifestEntry>,
    pub executables: Vec<ExecutableManifestEntry>,
    pub operations: Vec<OperationManifestEntry>,
    pub stores: Vec<StoreManifestEntry>,
    pub relationships_by_owner_span_id: IndexMap<String, ExecutableRelationships>,
    pub diagnostics: Vec<TraceEvidenceDiagnostic>,
}

/// The spans to select: at least one identifier, each at most once.
#[derive(Debug, Deserialize)]
#[serde(try_from = "Vec<SpanId>")]
pub struct SelectedSpanIds(Vec<String>);

impl TryFrom<Vec<SpanId>> for SelectedSpanIds {
    type Error = String;

    fn try_from(span_ids: Vec<SpanId>) -> Result<Self, Self::Error> {
        if span_ids.is_empty() {
            return Err("span_ids must contain at least one span ID".to_string());
        }
        let mut selected: Vec<String> = Vec::with_capacity(span_ids.len());
        for span_id in span_ids {
            if selected.contains(&span_id.0) {
                return Err("span_ids must not contain duplicates".to_string());
            }
            selected.push(span_id.0);
        }
        Ok(Self(selected))
    }
}

/// Exact span identities selected from one Attempt's bound trace.
#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SelectedSpanRequest {
    #[schema(value_type = Vec<String>, min_items = 1, pattern = "^[0-9a-f]{16}$")]
    span_ids: SelectedSpanIds,
}

/// Requested spans in caller order with explicit missing identities.
#[derive(Debug, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SelectedSpanEvidenceResponse {
    pub subject: AttemptEvidenceSubject,
    pub items: Vec<SelectedSpanEvidence>,
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub missing_span_ids: Vec<String>,
}

/// This feature's routes, relative to `/api/v1`.
pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(get_trace_evidence))
        .routes(routes!(get_attempt_evidence_manifest))
        .routes(routes!(get_attempt_span_evidence))
}

/// The evidence of one stored trace, or nothing when no span of it is stored.
pub async fn trace_evidence(
    state: &AppState,
    trace_id: &str,
) -> Result<Option<TraceEvidence>, ApiError> {
    let spans: Vec<NormalizedSpanEvidence> = repository::trace_spans(state, trace_id)
        .await?
        .iter()
        .map(Span::to_evidence)
        .collect();
    if spans.is_empty() {
        return Ok(None);
    }
    Ok(Some(assemble_trace_evidence(trace_id, spans)))
}

/// Get complete raw evidence and verified annotations for one trace.
#[utoipa::path(
    get,
    path = "/trace-evidence/{trace_id}",
    operation_id = "get_trace_evidence",
    tag = "trace-evidence",
    params(("trace_id" = String, Path, description = "The trace's identifier.", pattern = "^[0-9a-f]{32}$")),
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "The trace's evidence.", body = TraceEvidence),
        (status = 401, description = "No valid credential.", body = ErrorResponse),
        (status = 403, description = "The token lacks the evidence scope.", body = ErrorResponse),
        (status = 404, description = "Trace not found", body = ErrorResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn get_trace_evidence(
    State(state): State<AppState>,
    _access: EvidenceReadAccess,
    ApiPath(trace_id): ApiPath<TraceId>,
) -> Result<Json<TraceEvidence>, ApiError> {
    trace_evidence(&state, &trace_id.0)
        .await?
        .map(Json)
        .ok_or_else(|| ApiError::not_found("Trace not found"))
}

/// An Attempt's bound subject and the evidence of its trace.
///
/// `None` when any link is missing: the Attempt, its evidence binding, the
/// execution the binding names, that execution's trace, or the subject span
/// in it. A subject span that belongs to another service than the binding
/// names is also `None`: the evidence is not the bound execution's.
async fn attempt_trace_evidence(
    state: &AppState,
    attempt_id: String,
) -> Result<Option<(AttemptEvidenceSubject, TraceEvidence)>, ApiError> {
    let lookup = attempt_id.clone();
    let attempt = state
        .application_db
        .reader
        .call(move |connection| evaluation::repo::attempt_detail(connection, &lookup))
        .await?;
    let Some(reference) = attempt.and_then(|detail| detail.attempt.subject_evidence) else {
        return Ok(None);
    };

    let (service_namespace, service_name) = match &reference {
        ExecutionEvidenceReference::JunjoExecution(execution) => (
            execution.service_namespace.0.clone(),
            execution.service_name.0.clone(),
        ),
        ExecutionEvidenceReference::OtelSpan(span) => (
            span.service_namespace.0.clone(),
            span.service_name.0.clone(),
        ),
    };
    let subject = match &reference {
        ExecutionEvidenceReference::OtelSpan(span) => {
            let path = span_path(&service_name, &span.trace_id.0, &span.span_id.0);
            AttemptEvidenceSubject {
                attempt_id,
                trace_id: span.trace_id.0.clone(),
                span_id: span.span_id.0.clone(),
                detail_path: path.clone(),
                failure_path: path.clone(),
                trace_path: path,
                reference,
            }
        }
        ExecutionEvidenceReference::JunjoExecution(execution) => {
            let identity = ExecutionIdentity {
                service_namespace: service_namespace.clone(),
                service_name: service_name.clone(),
                executable_type: execution.executable_type,
                runtime_id: execution.runtime_id.0.clone(),
            };
            let Some(resolved) = execution_resolution::resolve(state, &identity).await? else {
                return Ok(None);
            };
            AttemptEvidenceSubject {
                attempt_id,
                trace_id: resolved.trace_id,
                span_id: resolved.span_id,
                detail_path: resolved.detail_path,
                failure_path: resolved.failure_path,
                trace_path: resolved.trace_path,
                reference,
            }
        }
    };

    let Some(evidence) = trace_evidence(state, &subject.trace_id).await? else {
        return Ok(None);
    };
    let Some(subject_span) = evidence
        .spans
        .iter()
        .find(|span| span.span_id == subject.span_id)
    else {
        return Ok(None);
    };
    let resource = &subject_span.resource_attributes_json;
    // A service without a namespace has the empty namespace.
    let stored_namespace = match resource.get("service.namespace") {
        None => Some(""),
        Some(value) => value.as_str(),
    };
    if get(resource, "service.name").as_str() != Some(service_name.as_str())
        || stored_namespace != Some(service_namespace.as_str())
    {
        return Ok(None);
    }
    Ok(Some((subject, evidence)))
}

fn attempt_evidence_not_found() -> ApiError {
    ApiError::not_found("Attempt evidence not found")
}

/// Get a payload-light trace manifest for one evaluation Attempt.
#[utoipa::path(
    get,
    path = "/trace-evidence/attempts/{attempt_id}/manifest",
    operation_id = "get_attempt_evidence_manifest",
    tag = "trace-evidence",
    params(("attempt_id" = String, Path, description = "The Attempt's identifier.", min_length = 1, max_length = 64)),
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "The manifest of the Attempt's bound trace.", body = AttemptEvidenceManifest),
        (status = 401, description = "No valid credential.", body = ErrorResponse),
        (status = 403, description = "The token lacks the evidence scope.", body = ErrorResponse),
        (status = 404, description = "Attempt or bound evidence not found", body = ErrorResponse),
        (status = 409, description = "More than one owner span records the bound execution.", body = ExecutionResolutionConflictResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn get_attempt_evidence_manifest(
    State(state): State<AppState>,
    _access: EvidenceReadAccess,
    ApiPath(attempt_id): ApiPath<RecordId>,
) -> Result<Json<AttemptEvidenceManifest>, ApiError> {
    let Some((subject, evidence)) = attempt_trace_evidence(&state, attempt_id.0).await? else {
        return Err(attempt_evidence_not_found());
    };
    let service_name = match &subject.reference {
        ExecutionEvidenceReference::JunjoExecution(execution) => &execution.service_name.0,
        ExecutionEvidenceReference::OtelSpan(span) => &span.service_name.0,
    };
    let manifest = assemble_attempt_evidence_manifest(service_name, &evidence);
    Ok(Json(AttemptEvidenceManifest {
        trace: manifest.trace,
        spans: manifest.spans,
        failures: manifest.failures,
        executables: manifest.executables,
        operations: manifest.operations,
        stores: manifest.stores,
        relationships_by_owner_span_id: manifest.relationships_by_owner_span_id,
        diagnostics: manifest.diagnostics,
        subject,
    }))
}

/// Get complete evidence for exact span IDs in an Attempt's bound trace.
#[utoipa::path(
    post,
    path = "/trace-evidence/attempts/{attempt_id}/spans",
    operation_id = "get_attempt_span_evidence",
    tag = "trace-evidence",
    params(("attempt_id" = String, Path, description = "The Attempt's identifier.", min_length = 1, max_length = 64)),
    request_body = SelectedSpanRequest,
    security(("EvaluationControlToken" = [])),
    responses(
        (status = 200, description = "The selected spans' evidence.", body = SelectedSpanEvidenceResponse),
        (status = 401, description = "No valid credential.", body = ErrorResponse),
        (status = 403, description = "The token lacks the evidence scope.", body = ErrorResponse),
        (status = 404, description = "Attempt or bound evidence not found", body = ErrorResponse),
        (status = 409, description = "More than one owner span records the bound execution.", body = ExecutionResolutionConflictResponse),
        (status = 422, description = "The request is not valid.", body = ErrorResponse),
    )
)]
pub async fn get_attempt_span_evidence(
    State(state): State<AppState>,
    _access: EvidenceReadAccess,
    ApiPath(attempt_id): ApiPath<RecordId>,
    ApiJson(request): ApiJson<SelectedSpanRequest>,
) -> Result<Json<SelectedSpanEvidenceResponse>, ApiError> {
    let Some((subject, evidence)) = attempt_trace_evidence(&state, attempt_id.0).await? else {
        return Err(attempt_evidence_not_found());
    };
    let selected = select_attempt_span_evidence(&evidence, &request.span_ids.0);
    Ok(Json(SelectedSpanEvidenceResponse {
        subject,
        items: selected.items,
        missing_span_ids: selected.missing_span_ids,
    }))
}

#[cfg(test)]
mod tests;
