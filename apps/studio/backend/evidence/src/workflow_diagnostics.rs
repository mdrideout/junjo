//! Assemble one Workflow Store diagnostic from preserved OTLP evidence.

use serde::Serialize;
use utoipa::ToSchema;

use crate::json::{JsonObject, display, get};
use crate::spans::attributes;
use crate::store_diagnostics::integrity::assemble_evidence_integrity;
use crate::store_diagnostics::reconstruction::{
    StoreSpanIndex, WORKFLOW_STORE_BOUNDARY, index_store_spans, reconstruct_store,
    store_evidence_spans,
};
use crate::store_diagnostics::schemas::{EvidenceDiagnostic, EvidenceIntegrity, StoreDetail};
use crate::telemetry_contract::{
    ACTIVE_TELEMETRY_CONTRACT_VERSION, is_active_contract_version, is_lower_hex, nonempty_text,
    portable_enum,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum WorkflowExecutableType {
    Workflow,
    Subflow,
}

/// Backend-authoritative Store projection for one Workflow executable.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct WorkflowStoreDiagnostic {
    pub trace_id: String,
    pub workflow_span_id: String,
    pub executable_type: WorkflowExecutableType,
    pub name: String,
    pub state: StoreDetail,
    pub integrity: EvidenceIntegrity,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkflowEvidenceErrorCode {
    UnsupportedContract,
    UnidentifiableWorkflow,
}

impl WorkflowEvidenceErrorCode {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::UnsupportedContract => "unsupported_contract",
            Self::UnidentifiableWorkflow => "unidentifiable_workflow",
        }
    }
}

/// A Workflow span cannot produce a supported semantic projection.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct WorkflowEvidenceError {
    pub code: WorkflowEvidenceErrorCode,
    pub message: String,
    pub diagnostics: Vec<EvidenceDiagnostic>,
}

impl WorkflowEvidenceError {
    fn from_diagnostic(code: WorkflowEvidenceErrorCode, issue: EvidenceDiagnostic) -> Self {
        Self {
            code,
            message: issue.message.clone(),
            diagnostics: vec![issue],
        }
    }
}

/// Validate one Workflow owner and independently reconstruct its Store.
///
/// `owner_span` must be one of `trace_spans`, passed as the same reference,
/// so its own events are not read twice. `store_index` is the index of
/// `trace_spans` when the caller has already built it. Without one, it is
/// built here.
pub fn assemble_workflow_store_diagnostic(
    owner_span: &JsonObject,
    trace_spans: &[&JsonObject],
    store_index: Option<&StoreSpanIndex<'_>>,
) -> Result<WorkflowStoreDiagnostic, WorkflowEvidenceError> {
    let attributes = attributes(owner_span);
    let executable_type =
        match portable_enum(get(attributes, "junjo.span_type"), &["workflow", "subflow"]) {
            Some("workflow") => WorkflowExecutableType::Workflow,
            Some(_) => WorkflowExecutableType::Subflow,
            None => {
                return Err(WorkflowEvidenceError {
                    code: WorkflowEvidenceErrorCode::UnidentifiableWorkflow,
                    message: "The selected span is not a Workflow or Subflow owner.".to_string(),
                    diagnostics: Vec::new(),
                });
            }
        };
    let version = get(attributes, "junjo.telemetry.contract_version");
    if !is_active_contract_version(version) {
        return Err(WorkflowEvidenceError::from_diagnostic(
            WorkflowEvidenceErrorCode::UnsupportedContract,
            EvidenceDiagnostic::new(
                "unsupported_contract",
                "junjo.telemetry.contract_version",
                format!(
                    "Expected telemetry contract {ACTIVE_TELEMETRY_CONTRACT_VERSION}; observed {}.",
                    display(version)
                ),
            ),
        ));
    }

    let identity = (
        get(owner_span, "trace_id").as_str(),
        get(owner_span, "span_id").as_str(),
        nonempty_text(get(owner_span, "name")),
    );
    let (Some(trace_id), Some(span_id), Some(name)) = identity else {
        return Err(WorkflowEvidenceError::from_diagnostic(
            WorkflowEvidenceErrorCode::UnidentifiableWorkflow,
            EvidenceDiagnostic::new(
                "required_identity_missing",
                "workflow.identity",
                "Workflow trace, span, or name identity is invalid.",
            ),
        ));
    };

    let built_index;
    let store_index = match store_index {
        Some(index) => index,
        None => {
            built_index = index_store_spans(trace_spans);
            &built_index
        }
    };
    let (evidence_spans, mut diagnostics) = store_evidence_spans(
        owner_span,
        get(attributes, WORKFLOW_STORE_BOUNDARY.store_id_attribute),
        store_index,
    );
    let reconstruction = reconstruct_store(attributes, &evidence_spans, &WORKFLOW_STORE_BOUNDARY);
    diagnostics.extend(reconstruction.diagnostics);
    let integrity = assemble_evidence_integrity(&evidence_spans, diagnostics);

    if !is_lower_hex(trace_id, 32) || !is_lower_hex(span_id, 16) {
        return Err(WorkflowEvidenceError {
            code: WorkflowEvidenceErrorCode::UnidentifiableWorkflow,
            message: "Workflow Store evidence cannot be represented.".to_string(),
            diagnostics: vec![EvidenceDiagnostic::new(
                "invalid_workflow_projection",
                "workflow.store",
                "Workflow trace and span identities must be exact lowercase hexadecimal text.",
            )],
        });
    }
    Ok(WorkflowStoreDiagnostic {
        trace_id: trace_id.to_string(),
        workflow_span_id: span_id.to_string(),
        executable_type,
        name: name.to_string(),
        state: reconstruction.detail,
        integrity,
    })
}
