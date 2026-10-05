//! Public contracts for lossless traces with verified semantic annotations.

use indexmap::IndexMap;
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

use crate::agent_diagnostics::schemas::{
    AgentExecutionSummary, AgentOperation, CancellationEvidence, CandidateEvidence, ExecutionError,
    NestedExecutableReference, Outcome, ParentExecutableReference,
};
use crate::json::{Json, JsonObject};
use crate::store_diagnostics::schemas::{
    EvidenceDiagnostic, EvidenceIntegrity, PayloadEvidence, ReconstructionStatus,
    StoreBoundaryDetail, StoreDetail, StoreTransition,
};
use crate::workflow_diagnostics::WorkflowExecutableType;

/// One normalized span, including every field preserved by Studio storage.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct NormalizedSpanEvidence {
    pub trace_id: String,
    pub span_id: String,
    #[schema(required)]
    pub parent_span_id: Option<String>,
    pub service_name: String,
    pub name: String,
    pub kind: String,
    pub start_time: String,
    pub end_time: String,
    pub status_code: String,
    pub status_message: String,
    #[schema(value_type = Object)]
    pub attributes_json: JsonObject,
    pub events_json: Vec<Json>,
    pub links_json: Vec<Json>,
    pub trace_flags: i64,
    #[schema(required)]
    pub trace_state: Option<String>,
    pub dropped_attributes_count: i64,
    pub dropped_events_count: i64,
    pub dropped_links_count: i64,
    #[schema(value_type = Object)]
    pub resource_attributes_json: JsonObject,
    pub resource_dropped_attributes_count: i64,
}

impl NormalizedSpanEvidence {
    /// The span as the loosely typed object the semantic assemblers read.
    pub fn to_object(&self) -> JsonObject {
        match serde_json::to_value(self) {
            Ok(Json::Object(object)) => object,
            _ => JsonObject::new(),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum AgentExecutableType {
    Agent,
}

/// What a Store is to one execution: the application state it works on, or
/// an Agent's private runtime state.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum StoreRole {
    Application,
    Runtime,
}

/// Verified Agent owner facts; operations and Store evidence remain indexed.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AgentExecutableAnnotation {
    #[schema(inline)]
    pub executable_type: AgentExecutableType,
    pub owner_span_id: String,
    pub runtime_id: String,
    pub stores: IndexMap<StoreRole, StoreBoundaryDetail>,
    pub summary: AgentExecutionSummary,
    pub definition: PayloadEvidence,
    pub input: Option<PayloadEvidence>,
    pub output: Option<PayloadEvidence>,
    pub input_candidate: Option<CandidateEvidence>,
    pub history_candidate: Option<CandidateEvidence>,
    pub error: Option<ExecutionError>,
    pub cancellation: Option<CancellationEvidence>,
    pub integrity: EvidenceIntegrity,
}

/// Verified Workflow owner facts; the Store is indexed independently.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct WorkflowExecutableAnnotation {
    #[schema(inline)]
    pub executable_type: WorkflowExecutableType,
    pub owner_span_id: String,
    pub name: String,
    pub definition_id: Option<String>,
    pub runtime_id: Option<String>,
    pub structural_id: Option<String>,
    pub stores: IndexMap<StoreRole, StoreBoundaryDetail>,
    pub integrity: EvidenceIntegrity,
}

/// The kind of executable that owns a Store or an annotation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum OwnerExecutableType {
    Workflow,
    Subflow,
    Agent,
}

impl From<WorkflowExecutableType> for OwnerExecutableType {
    fn from(executable_type: WorkflowExecutableType) -> Self {
        match executable_type {
            WorkflowExecutableType::Workflow => Self::Workflow,
            WorkflowExecutableType::Subflow => Self::Subflow,
        }
    }
}

/// One executable owner's annotation, discriminated by `executable_type`.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(untagged)]
#[schema(discriminator(property_name = "executable_type", mapping(
    ("agent" = "#/components/schemas/AgentExecutableAnnotation"),
    ("subflow" = "#/components/schemas/WorkflowExecutableAnnotation"),
    ("workflow" = "#/components/schemas/WorkflowExecutableAnnotation"),
)))]
pub enum ExecutableAnnotation {
    Agent(Box<AgentExecutableAnnotation>),
    Workflow(Box<WorkflowExecutableAnnotation>),
}

impl ExecutableAnnotation {
    pub fn executable_type(&self) -> OwnerExecutableType {
        match self {
            Self::Agent(_) => OwnerExecutableType::Agent,
            Self::Workflow(annotation) => annotation.executable_type.into(),
        }
    }

    pub fn runtime_id(&self) -> Option<&str> {
        match self {
            Self::Agent(annotation) => Some(&annotation.runtime_id),
            Self::Workflow(annotation) => annotation.runtime_id.as_deref(),
        }
    }

    pub fn stores(&self) -> &IndexMap<StoreRole, StoreBoundaryDetail> {
        match self {
            Self::Agent(annotation) => &annotation.stores,
            Self::Workflow(annotation) => &annotation.stores,
        }
    }

    pub fn integrity(&self) -> &EvidenceIntegrity {
        match self {
            Self::Agent(annotation) => &annotation.integrity,
            Self::Workflow(annotation) => &annotation.integrity,
        }
    }
}

/// One shared transition log, keyed by the physical Store identity.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct StoreAnnotation {
    pub store_id: String,
    pub transitions: Vec<StoreTransition>,
}

/// One selected execution's Store role and independently verified interval.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct StoreExecutionDetail {
    pub owner_span_id: String,
    #[schema(inline)]
    pub role: StoreRole,
    pub detail: StoreDetail,
}

/// Semantic executable boundaries discovered from one owner.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ExecutableRelationships {
    pub parent: Option<ParentExecutableReference>,
    #[schema(required = false)]
    pub nested: Vec<NestedExecutableReference>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum DiagnosticScope {
    Trace,
    Executable,
}

/// A diagnostic scoped to the trace or to one executable owner.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct TraceEvidenceDiagnostic {
    #[schema(inline)]
    pub scope: DiagnosticScope,
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub owner_span_id: Option<String>,
    pub issue: EvidenceDiagnostic,
}

/// Complete normalized telemetry plus generic verified annotations.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct TraceEvidence {
    pub trace_id: String,
    pub spans: Vec<NormalizedSpanEvidence>,
    pub executables_by_span_id: IndexMap<String, ExecutableAnnotation>,
    pub operations_by_owner_runtime_id: IndexMap<String, IndexMap<String, AgentOperation>>,
    pub stores_by_id: IndexMap<String, StoreAnnotation>,
    pub relationships_by_owner_span_id: IndexMap<String, ExecutableRelationships>,
    pub diagnostics: Vec<TraceEvidenceDiagnostic>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum SemanticSpanKind {
    Agent,
    Workflow,
    Subflow,
    Node,
    RunConcurrent,
    Model,
    Tool,
    Span,
}

/// Bounded identity and shape facts for one trace.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct TraceManifestSummary {
    #[schema(pattern = "^[0-9a-f]{32}$")]
    pub trace_id: String,
    #[schema(minimum = 1)]
    pub span_count: usize,
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub root_span_ids: Vec<String>,
}

/// Small selectable projection for one span.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SpanManifestEntry {
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub span_id: String,
    #[schema(required, pattern = "^[0-9a-f]{16}$")]
    pub parent_span_id: Option<String>,
    pub name: String,
    #[schema(inline)]
    pub semantic_kind: SemanticSpanKind,
    pub status_code: String,
    pub start_time: String,
    pub end_time: String,
    pub failed: bool,
    #[schema(pattern = "^/")]
    pub span_path: String,
}

/// Failure signal without the span's large forensic payload fields.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct FailureSpanManifestEntry {
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub span_id: String,
    #[schema(required, pattern = "^[0-9a-f]{16}$")]
    pub parent_span_id: Option<String>,
    pub name: String,
    #[schema(inline)]
    pub semantic_kind: SemanticSpanKind,
    pub status_code: String,
    pub start_time: String,
    pub end_time: String,
    #[schema(required)]
    pub exception_type: Option<String>,
    #[schema(required)]
    pub exception_message: Option<String>,
    pub stacktrace_available: bool,
    #[schema(required, pattern = "^[0-9a-f]{16}$")]
    pub owner_span_id: Option<String>,
    #[schema(required)]
    pub owner_runtime_id: Option<String>,
    #[schema(pattern = "^/")]
    pub span_path: String,
}

/// Compact verified executable facts for triage.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ExecutableManifestEntry {
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub owner_span_id: String,
    #[schema(inline)]
    pub executable_type: OwnerExecutableType,
    pub name: String,
    #[schema(required)]
    pub runtime_id: Option<String>,
    pub store_ids: IndexMap<StoreRole, Option<String>>,
    #[schema(required, inline)]
    pub outcome: Option<Outcome>,
    pub status_code: String,
    pub failed: bool,
    pub integrity: EvidenceIntegrity,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum OperationType {
    ModelRequest,
    Tool,
}

/// Compact verified Agent model or Tool operation facts.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct OperationManifestEntry {
    #[schema(required, pattern = "^[0-9a-f]{16}$")]
    pub owner_span_id: Option<String>,
    #[schema(required)]
    pub owner_runtime_id: Option<String>,
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub span_id: String,
    #[schema(inline)]
    pub operation_type: OperationType,
    pub name: String,
    #[schema(inline)]
    pub outcome: Outcome,
    #[schema(required, minimum = 0)]
    pub duration_ns: Option<i64>,
    #[schema(required)]
    pub error_type: Option<String>,
    #[schema(required)]
    pub error_message: Option<String>,
}

/// Compact Store reconstruction and integrity facts.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct StoreManifestEntry {
    #[schema(required)]
    pub store_id: Option<String>,
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub owner_span_id: String,
    #[schema(required)]
    pub owner_runtime_id: Option<String>,
    #[schema(inline)]
    pub owner_executable_type: OwnerExecutableType,
    #[schema(inline)]
    pub role: StoreRole,
    #[schema(required, minimum = 0)]
    pub sequence_start: Option<i64>,
    #[schema(required, minimum = 0)]
    pub sequence_end: Option<i64>,
    pub available: bool,
    #[schema(minimum = 0)]
    pub transition_count: i64,
    pub reconstructable: bool,
    #[schema(inline)]
    pub reconstruction_status: ReconstructionStatus,
    pub integrity: EvidenceIntegrity,
}

/// The trace-aware middle layer between an Attempt and complete evidence,
/// without the Attempt subject. The caller resolved the subject and adds it.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct AttemptManifest {
    pub trace: TraceManifestSummary,
    pub spans: Vec<SpanManifestEntry>,
    pub failures: Vec<FailureSpanManifestEntry>,
    pub executables: Vec<ExecutableManifestEntry>,
    pub operations: Vec<OperationManifestEntry>,
    pub stores: Vec<StoreManifestEntry>,
    pub relationships_by_owner_span_id: IndexMap<String, ExecutableRelationships>,
    pub diagnostics: Vec<TraceEvidenceDiagnostic>,
}

/// One complete span plus semantic evidence directly owned by it.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SelectedSpanEvidence {
    pub span: NormalizedSpanEvidence,
    #[schema(required)]
    pub executable: Option<ExecutableAnnotation>,
    #[schema(required)]
    pub operation: Option<AgentOperation>,
    pub stores: Vec<StoreExecutionDetail>,
    #[schema(required)]
    pub relationships: Option<ExecutableRelationships>,
    pub diagnostics: Vec<TraceEvidenceDiagnostic>,
}

/// Requested spans in caller order with explicit missing identities.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct SelectedSpans {
    pub items: Vec<SelectedSpanEvidence>,
    pub missing_span_ids: Vec<String>,
}
