//! Public semantic API contracts for Agent execution diagnostics.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

use crate::store_diagnostics::schemas::{
    EvidenceDiagnostic, EvidenceIntegrity, PayloadEvidence, StoreDetail,
};
use crate::telemetry_contract::is_lower_hex;
use crate::timestamps::Timestamp;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ServiceIdentity {
    pub namespace: String,
    #[schema(min_length = 1)]
    pub name: String,
    #[schema(min_length = 1)]
    pub version: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AgentLimits {
    #[schema(minimum = 1, maximum = 9007199254740991_i64)]
    pub model_requests: i64,
    #[schema(minimum = 1, maximum = 9007199254740991_i64)]
    pub tool_calls: i64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ToolCallCounts {
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub requested: i64,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub admitted: i64,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub started: i64,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub completed: i64,
}

impl ToolCallCounts {
    /// Each stage can only be reached by calls that reached the one before.
    pub fn is_monotonic(&self) -> bool {
        self.completed <= self.started
            && self.started <= self.admitted
            && self.admitted <= self.requested
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AgentCounts {
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub operations: i64,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub model_requests: i64,
    pub tool_calls: ToolCallCounts,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UsageAggregate {
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub sum: i64,
    #[schema(minimum = 1, maximum = 9007199254740991_i64)]
    pub observations: i64,
}

/// The token usage fields a model response may report.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, ToSchema)]
pub enum UsageField {
    #[serde(rename = "inputTokens")]
    InputTokens,
    #[serde(rename = "outputTokens")]
    OutputTokens,
    #[serde(rename = "cachedInputTokens")]
    CachedInputTokens,
    #[serde(rename = "reasoningTokens")]
    ReasoningTokens,
    #[serde(rename = "totalTokens")]
    TotalTokens,
}

impl UsageField {
    pub const ALL: [Self; 5] = [
        Self::InputTokens,
        Self::OutputTokens,
        Self::CachedInputTokens,
        Self::ReasoningTokens,
        Self::TotalTokens,
    ];

    /// The member name used in usage payloads.
    pub fn contract_name(self) -> &'static str {
        match self {
            Self::InputTokens => "inputTokens",
            Self::OutputTokens => "outputTokens",
            Self::CachedInputTokens => "cachedInputTokens",
            Self::ReasoningTokens => "reasoningTokens",
            Self::TotalTokens => "totalTokens",
        }
    }

    pub fn from_contract_name(name: &str) -> Option<Self> {
        Self::ALL
            .into_iter()
            .find(|field| field.contract_name() == name)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AgentUsage {
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub model_responses: i64,
    pub fields: BTreeMap<UsageField, UsageAggregate>,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ModelUsage {
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub input_tokens: Option<i64>,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub output_tokens: Option<i64>,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub cached_input_tokens: Option<i64>,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub reasoning_tokens: Option<i64>,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub total_tokens: Option<i64>,
}

impl ModelUsage {
    /// The reported fields, in contract order.
    pub fn reported(&self) -> impl Iterator<Item = (UsageField, i64)> {
        [
            (UsageField::InputTokens, self.input_tokens),
            (UsageField::OutputTokens, self.output_tokens),
            (UsageField::CachedInputTokens, self.cached_input_tokens),
            (UsageField::ReasoningTokens, self.reasoning_tokens),
            (UsageField::TotalTokens, self.total_tokens),
        ]
        .into_iter()
        .filter_map(|(field, value)| value.map(|value| (field, value)))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum Outcome {
    Completed,
    Failed,
    Cancelled,
}

impl Outcome {
    pub const NAMES: [&'static str; 3] = ["completed", "failed", "cancelled"];

    pub fn from_name(name: &str) -> Option<Self> {
        match name {
            "completed" => Some(Self::Completed),
            "failed" => Some(Self::Failed),
            "cancelled" => Some(Self::Cancelled),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum TerminationReason {
    FinalOutput,
    InputValidationError,
    HistoryValidationError,
    LimitExceeded,
    ModelError,
    ModelResponseError,
    UnknownTool,
    ToolInputValidationError,
    ToolError,
    ToolOutputValidationError,
    OutputValidationError,
    Cancelled,
    InternalError,
}

impl TerminationReason {
    pub fn from_name(name: &str) -> Option<Self> {
        Some(match name {
            "final_output" => Self::FinalOutput,
            "input_validation_error" => Self::InputValidationError,
            "history_validation_error" => Self::HistoryValidationError,
            "limit_exceeded" => Self::LimitExceeded,
            "model_error" => Self::ModelError,
            "model_response_error" => Self::ModelResponseError,
            "unknown_tool" => Self::UnknownTool,
            "tool_input_validation_error" => Self::ToolInputValidationError,
            "tool_error" => Self::ToolError,
            "tool_output_validation_error" => Self::ToolOutputValidationError,
            "output_validation_error" => Self::OutputValidationError,
            "cancelled" => Self::Cancelled,
            "internal_error" => Self::InternalError,
            _ => return None,
        })
    }

    /// The only outcome an Agent with this termination reason can have.
    pub fn expected_outcome(self) -> Outcome {
        match self {
            Self::FinalOutput => Outcome::Completed,
            Self::Cancelled => Outcome::Cancelled,
            _ => Outcome::Failed,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AgentExecutionSummary {
    #[schema(pattern = "^[0-9a-f]{32}$")]
    pub trace_id: String,
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub agent_span_id: String,
    pub service: ServiceIdentity,
    #[schema(min_length = 1)]
    pub agent_key: String,
    #[schema(min_length = 1)]
    pub agent_name: String,
    #[schema(pattern = "^agent_sha256:[0-9a-f]{64}$")]
    pub structural_id: String,
    #[schema(min_length = 1)]
    pub definition_id: String,
    #[schema(min_length = 1)]
    pub runtime_id: String,
    #[schema(value_type = String, format = DateTime)]
    pub start_time: Timestamp,
    #[schema(value_type = String, format = DateTime)]
    pub end_time: Timestamp,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub duration_ns: i64,
    #[schema(inline)]
    pub outcome: Outcome,
    #[schema(inline)]
    pub termination_reason: TerminationReason,
    pub limits: AgentLimits,
    pub counts: AgentCounts,
    pub usage: AgentUsage,
}

impl AgentExecutionSummary {
    /// The relationships every representable summary satisfies.
    pub fn validate(&self) -> Result<(), &'static str> {
        if !self.counts.tool_calls.is_monotonic() {
            return Err("Tool counts must satisfy completed <= started <= admitted <= requested");
        }
        if self.outcome != self.termination_reason.expected_outcome() {
            return Err("Agent outcome does not match its termination reason");
        }
        if self.counts.operations < self.counts.model_requests {
            return Err("operation count cannot be smaller than model request count");
        }
        if self.counts.model_requests > self.limits.model_requests {
            return Err("model request count exceeds its limit");
        }
        if self.counts.tool_calls.admitted > self.limits.tool_calls {
            return Err("admitted Tool count exceeds its limit");
        }
        if self.usage.model_responses > self.counts.model_requests {
            return Err("validated model responses cannot exceed model requests");
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum UnavailableReason {
    Cancelled,
    NotReturned,
    NotInvoked,
    ServiceFailed,
    NotJsonSerializable,
    ContractEvidenceMissing,
}

impl UnavailableReason {
    pub fn from_name(name: &str) -> Option<Self> {
        Some(match name {
            "cancelled" => Self::Cancelled,
            "not_returned" => Self::NotReturned,
            "not_invoked" => Self::NotInvoked,
            "service_failed" => Self::ServiceFailed,
            "not_json_serializable" => Self::NotJsonSerializable,
            _ => return None,
        })
    }
}

/// A value a producer attempted to validate. It is either available with its
/// payload, or unavailable with the reason.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CandidateEvidence {
    pub available: bool,
    pub payload: Option<PayloadEvidence>,
    #[schema(inline)]
    pub unavailable_reason: Option<UnavailableReason>,
}

impl CandidateEvidence {
    pub fn available(payload: PayloadEvidence) -> Self {
        Self {
            available: true,
            payload: Some(payload),
            unavailable_reason: None,
        }
    }

    pub fn unavailable(reason: UnavailableReason) -> Self {
        Self {
            available: false,
            payload: None,
            unavailable_reason: Some(reason),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ExecutionError {
    #[serde(rename = "type")]
    #[schema(min_length = 1)]
    pub error_type: String,
    pub message: Option<String>,
    pub stacktrace: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CancellationEvidence {
    #[schema(min_length = 1)]
    pub reason: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum Admission {
    Admitted,
    NotAdmitted,
    Unknown,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum RequestedToolCallReason {
    ExecutionInterrupted,
    StoreEvidenceUnavailable,
    ToolInputValidationError,
    UnknownTool,
    LimitExceeded,
    BatchPreflightRejected,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct RequestedToolCall {
    #[schema(min_length = 1)]
    pub call_id: String,
    #[schema(minimum = 1, maximum = 9007199254740991_i64)]
    pub ordinal: i64,
    #[schema(min_length = 1)]
    pub tool_name: String,
    pub observed_tool_operation: bool,
    #[schema(inline)]
    pub admission: Admission,
    #[schema(inline)]
    pub reason: Option<RequestedToolCallReason>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ResponseType {
    FinalOutput,
    ToolCalls,
}

impl ResponseType {
    pub const NAMES: [&'static str; 2] = ["final_output", "tool_calls"];

    pub fn from_name(name: &str) -> Option<Self> {
        match name {
            "final_output" => Some(Self::FinalOutput),
            "tool_calls" => Some(Self::ToolCalls),
            _ => None,
        }
    }
}

/// The discriminator value of a Model operation.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, ToSchema)]
pub enum ModelOperationType {
    #[default]
    #[serde(rename = "model_request")]
    ModelRequest,
}

/// The discriminator value of a Tool operation.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, ToSchema)]
pub enum ToolOperationType {
    #[default]
    #[serde(rename = "tool")]
    Tool,
}

#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ModelOperation {
    #[schema(inline)]
    pub operation_type: ModelOperationType,
    #[schema(minimum = 1, maximum = 9007199254740991_i64)]
    pub sequence: i64,
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub span_id: String,
    #[schema(value_type = String, format = DateTime)]
    pub start_time: Timestamp,
    #[schema(value_type = String, format = DateTime)]
    pub end_time: Timestamp,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub duration_ns: i64,
    #[schema(minimum = 1, maximum = 9007199254740991_i64)]
    pub ordinal: i64,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub state_revision: i64,
    #[schema(min_length = 1)]
    pub driver_key: String,
    #[schema(min_length = 1)]
    pub provider: String,
    #[schema(min_length = 1)]
    pub model_name: String,
    pub request: PayloadEvidence,
    pub response_candidate: CandidateEvidence,
    #[schema(inline)]
    pub response_type: Option<ResponseType>,
    pub response: Option<PayloadEvidence>,
    pub usage: Option<ModelUsage>,
    #[schema(required = false)]
    pub requested_tool_calls: Vec<RequestedToolCall>,
    #[schema(inline)]
    pub outcome: Outcome,
    pub error: Option<ExecutionError>,
    pub cancellation: Option<CancellationEvidence>,
}

impl ModelOperation {
    /// The shape every representable Model operation satisfies.
    pub fn validate(&self) -> Result<(), &'static str> {
        if !is_lower_hex(&self.span_id, 16) {
            return Err("operation span ID must be 16 lowercase hexadecimal characters");
        }
        validate_operation_outcome(
            self.outcome,
            self.error.is_some(),
            self.cancellation.is_some(),
        )?;
        if self.response_type.is_none() != self.response.is_none() {
            return Err("validated model response type and payload must be present together");
        }
        if self.outcome == Outcome::Completed && self.response.is_none() {
            return Err("completed Model operation requires a validated response");
        }
        if self.outcome != Outcome::Completed && (self.response.is_some() || self.usage.is_some()) {
            return Err("failed or cancelled Model operation cannot carry response evidence");
        }
        if self.response_type != Some(ResponseType::ToolCalls)
            && !self.requested_tool_calls.is_empty()
        {
            return Err("requested Tool calls require a validated Tool-calls response");
        }
        if self.response_type.is_none() && self.usage.is_some() {
            return Err("usage requires a validated model response");
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ToolOperation {
    #[schema(inline)]
    pub operation_type: ToolOperationType,
    #[schema(minimum = 1, maximum = 9007199254740991_i64)]
    pub sequence: i64,
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub span_id: String,
    #[schema(value_type = String, format = DateTime)]
    pub start_time: Timestamp,
    #[schema(value_type = String, format = DateTime)]
    pub end_time: Timestamp,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub duration_ns: i64,
    #[schema(min_length = 1)]
    pub call_id: String,
    #[schema(minimum = 1, maximum = 9007199254740991_i64)]
    pub ordinal: i64,
    #[schema(min_length = 1)]
    pub tool_name: String,
    #[schema(pattern = "^tool_sha256:[0-9a-f]{64}$")]
    pub tool_structural_id: String,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub state_revision_before: i64,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub state_revision_after: Option<i64>,
    pub requested_arguments: PayloadEvidence,
    pub arguments: Option<PayloadEvidence>,
    pub result_candidate: CandidateEvidence,
    pub result: Option<PayloadEvidence>,
    #[schema(inline)]
    pub outcome: Outcome,
    pub error: Option<ExecutionError>,
    pub cancellation: Option<CancellationEvidence>,
}

impl ToolOperation {
    /// The shape every representable Tool operation satisfies.
    pub fn validate(&self) -> Result<(), &'static str> {
        if !is_lower_hex(&self.span_id, 16) {
            return Err("operation span ID must be 16 lowercase hexadecimal characters");
        }
        if !is_structural_id(&self.tool_structural_id, "tool_sha256:") {
            return Err("Tool structural ID is invalid");
        }
        validate_operation_outcome(
            self.outcome,
            self.error.is_some(),
            self.cancellation.is_some(),
        )?;
        if self.outcome == Outcome::Completed {
            if self.arguments.is_none()
                || self.result.is_none()
                || self.state_revision_after.is_none()
            {
                return Err(
                    "completed Tool operation requires validated arguments/result and revision",
                );
            }
        } else if self.result.is_some() || self.state_revision_after.is_some() {
            return Err(
                "failed or cancelled Tool operation cannot carry committed result evidence",
            );
        }
        if self.result.is_none() != self.state_revision_after.is_none() {
            return Err("Tool result and committed revision must be present together");
        }
        Ok(())
    }
}

/// One operation an Agent performed, discriminated by `operation_type`.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(untagged)]
#[schema(discriminator(property_name = "operation_type", mapping(
    ("model_request" = "#/components/schemas/ModelOperation"),
    ("tool" = "#/components/schemas/ToolOperation"),
)))]
pub enum AgentOperation {
    Model(ModelOperation),
    Tool(ToolOperation),
}

impl AgentOperation {
    pub fn sequence(&self) -> i64 {
        match self {
            Self::Model(operation) => operation.sequence,
            Self::Tool(operation) => operation.sequence,
        }
    }

    pub fn span_id(&self) -> &str {
        match self {
            Self::Model(operation) => &operation.span_id,
            Self::Tool(operation) => &operation.span_id,
        }
    }

    pub fn as_model(&self) -> Option<&ModelOperation> {
        match self {
            Self::Model(operation) => Some(operation),
            Self::Tool(_) => None,
        }
    }

    pub fn as_tool(&self) -> Option<&ToolOperation> {
        match self {
            Self::Tool(operation) => Some(operation),
            Self::Model(_) => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ExecutableType {
    Workflow,
    Subflow,
    Node,
    RunConcurrent,
    Agent,
}

impl ExecutableType {
    pub const NAMES: [&'static str; 5] = ["workflow", "subflow", "node", "run_concurrent", "agent"];

    pub fn from_name(name: &str) -> Option<Self> {
        Some(match name {
            "workflow" => Self::Workflow,
            "subflow" => Self::Subflow,
            "node" => Self::Node,
            "run_concurrent" => Self::RunConcurrent,
            "agent" => Self::Agent,
            _ => return None,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ParentExecutableReference {
    #[schema(inline)]
    pub executable_type: ExecutableType,
    #[schema(pattern = "^[0-9a-f]{32}$")]
    pub trace_id: String,
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub physical_parent_span_id: String,
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub span_id: String,
    pub service: ServiceIdentity,
    #[schema(min_length = 1)]
    pub definition_id: String,
    #[schema(min_length = 1)]
    pub runtime_id: String,
    #[schema(min_length = 1)]
    pub structural_id: String,
    #[schema(min_length = 1)]
    pub name: String,
}

/// The executable kinds a Tool operation can directly parent.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum NestedExecutableType {
    Workflow,
    Agent,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct NestedExecutableReference {
    #[schema(inline)]
    pub executable_type: NestedExecutableType,
    #[schema(minimum = 1, maximum = 9007199254740991_i64)]
    pub parent_operation_sequence: i64,
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub parent_operation_span_id: String,
    #[schema(pattern = "^[0-9a-f]{32}$")]
    pub trace_id: String,
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub span_id: String,
    pub service: ServiceIdentity,
    #[schema(min_length = 1)]
    pub definition_id: String,
    #[schema(min_length = 1)]
    pub runtime_id: String,
    #[schema(min_length = 1)]
    pub structural_id: String,
    #[schema(min_length = 1)]
    pub name: String,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct AgentExecutionDetail {
    pub summary: AgentExecutionSummary,
    pub definition: PayloadEvidence,
    pub input: Option<PayloadEvidence>,
    pub output: Option<PayloadEvidence>,
    pub input_candidate: Option<CandidateEvidence>,
    pub history_candidate: Option<CandidateEvidence>,
    pub operations: Vec<AgentOperation>,
    pub state: StoreDetail,
    pub application_state: StoreDetail,
    pub parent_executable: Option<ParentExecutableReference>,
    pub nested_executables: Vec<NestedExecutableReference>,
    pub error: Option<ExecutionError>,
    pub cancellation: Option<CancellationEvidence>,
    pub integrity: EvidenceIntegrity,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum AgentEvidenceErrorCode {
    UnsupportedContract,
    UnidentifiableAgent,
}

impl AgentEvidenceErrorCode {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::UnsupportedContract => "unsupported_contract",
            Self::UnidentifiableAgent => "unidentifiable_agent",
        }
    }
}

/// A semantic Agent query cannot return a typed result.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
#[schema(as = AgentEvidenceErrorResponse)]
pub struct AgentEvidenceError {
    #[schema(inline)]
    pub code: AgentEvidenceErrorCode,
    #[schema(min_length = 1)]
    pub message: String,
    #[schema(required = false)]
    pub diagnostics: Vec<EvidenceDiagnostic>,
}

impl AgentEvidenceError {
    pub fn unidentifiable(
        message: impl Into<String>,
        diagnostics: Vec<EvidenceDiagnostic>,
    ) -> Self {
        Self {
            code: AgentEvidenceErrorCode::UnidentifiableAgent,
            message: message.into(),
            diagnostics,
        }
    }
}

/// A structural fingerprint: the prefix followed by 64 lowercase hex digits.
pub fn is_structural_id(value: &str, prefix: &str) -> bool {
    value
        .strip_prefix(prefix)
        .is_some_and(|digest| is_lower_hex(digest, 64))
}

/// An outcome and its error and cancellation evidence must agree.
fn validate_operation_outcome(
    outcome: Outcome,
    has_error: bool,
    has_cancellation: bool,
) -> Result<(), &'static str> {
    match outcome {
        Outcome::Completed if has_error || has_cancellation => {
            Err("completed execution cannot contain error or cancellation evidence")
        }
        Outcome::Failed if has_cancellation => {
            Err("failed execution cannot contain cancellation evidence")
        }
        Outcome::Cancelled if has_error || !has_cancellation => {
            Err("cancelled execution requires only cancellation evidence")
        }
        _ => Ok(()),
    }
}
