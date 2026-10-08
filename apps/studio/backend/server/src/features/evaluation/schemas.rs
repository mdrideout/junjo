//! The evaluation API's request and response types.
//!
//! Every value a caller sends is checked as it is deserialized, by the type
//! of its field. A response carries stored values as plain text and numbers.

use junjo_evidence::telemetry_contract::is_lower_hex;
use serde::de::Error as _;
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::Value;
use utoipa::ToSchema;

pub use crate::features::execution_resolution::ExecutableType;
use crate::text;
use crate::timestamps::UtcSeconds;

const MAX_KEY_BYTES: usize = 128;
const MAX_NAME_BYTES: usize = 256;
const MAX_DESCRIPTION_BYTES: usize = 2_048;
const MAX_REASON_BYTES: usize = 4_096;
const MAX_EXECUTION_IDENTITY_BYTES: usize = 256;
const MAX_RECORD_ID_CHARACTERS: usize = 64;
const MAX_VERSION: i64 = 2_147_483_647;
const MAX_DURATION_MS: i64 = 86_400_000;
/// The most bytes the canonical text of one JSON document may have.
pub const MAX_JSON_BYTES: usize = 16_384;
/// The most cases one dataset holds.
pub const MAX_CASES_PER_DATASET: i64 = 100;

/// Check text a caller sends. It has no surrounding whitespace and is at most
/// `max_bytes` UTF-8 bytes. Text that must be `nonempty` also contains
/// something other than whitespace.
fn validate_text(
    value: String,
    field_name: &str,
    max_bytes: usize,
    nonempty: bool,
) -> Result<String, String> {
    let trimmed = text::trimmed(&value);
    if nonempty && trimmed.is_empty() {
        return Err(format!("{field_name} must not be blank"));
    }
    if trimmed.len() != value.len() {
        return Err(format!(
            "{field_name} must not contain surrounding whitespace"
        ));
    }
    if value.len() > max_bytes {
        return Err(format!(
            "{field_name} must be at most {max_bytes} UTF-8 bytes"
        ));
    }
    Ok(value)
}

/// A machine key: 1 to 128 bytes.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "String")]
pub struct KeyText(pub String);

impl TryFrom<String> for KeyText {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        validate_text(value, "key", MAX_KEY_BYTES, true).map(Self)
    }
}

/// A human-readable name: 1 to 256 bytes.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "String")]
pub struct NameText(pub String);

impl TryFrom<String> for NameText {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        validate_text(value, "name", MAX_NAME_BYTES, true).map(Self)
    }
}

/// A description: at most 2,048 bytes. It may be empty.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "String")]
pub struct DescriptionText(pub String);

impl TryFrom<String> for DescriptionText {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        validate_text(value, "description", MAX_DESCRIPTION_BYTES, false).map(Self)
    }
}

/// Why an attempt ended as it did: 1 to 4,096 bytes.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "String")]
pub struct ReasonText(pub String);

impl TryFrom<String> for ReasonText {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        validate_text(value, "reason", MAX_REASON_BYTES, true).map(Self)
    }
}

/// An exact `service.namespace`: at most 256 bytes. Empty means the service
/// has no namespace.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "String")]
pub struct ServiceNamespaceText(pub String);

impl TryFrom<String> for ServiceNamespaceText {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        validate_text(
            value,
            "service_namespace",
            MAX_EXECUTION_IDENTITY_BYTES,
            false,
        )
        .map(Self)
    }
}

/// One part of an execution's identity, such as its service name or runtime
/// identity: 1 to 256 bytes.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "String")]
pub struct ExecutionIdentityText(pub String);

impl TryFrom<String> for ExecutionIdentityText {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        validate_text(
            value,
            "execution identity",
            MAX_EXECUTION_IDENTITY_BYTES,
            true,
        )
        .map(Self)
    }
}

/// A record identifier as a caller sends it: 1 to 64 characters.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "String")]
pub struct RecordId(pub String);

impl TryFrom<String> for RecordId {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        if value.is_empty() || value.chars().count() > MAX_RECORD_ID_CHARACTERS {
            return Err(format!(
                "record ID must be 1 to {MAX_RECORD_ID_CHARACTERS} characters"
            ));
        }
        Ok(Self(value))
    }
}

/// A source revision: a commit hash of 40 or 64 lowercase hexadecimal digits.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "String")]
pub struct SourceRevision(pub String);

impl TryFrom<String> for SourceRevision {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        if !is_lower_hex(&value, 40) && !is_lower_hex(&value, 64) {
            return Err(
                "source_revision must be 40 or 64 lowercase hexadecimal digits".to_string(),
            );
        }
        Ok(Self(value))
    }
}

/// A trace identifier: 32 lowercase hexadecimal digits.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "String")]
pub struct TraceId(pub String);

impl TryFrom<String> for TraceId {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        if !is_lower_hex(&value, 32) {
            return Err("trace_id must be 32 lowercase hexadecimal digits".to_string());
        }
        Ok(Self(value))
    }
}

/// A span identifier: 16 lowercase hexadecimal digits.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "String")]
pub struct SpanId(pub String);

impl TryFrom<String> for SpanId {
    type Error = String;

    fn try_from(value: String) -> Result<Self, Self::Error> {
        if !is_lower_hex(&value, 16) {
            return Err("span_id must be 16 lowercase hexadecimal digits".to_string());
        }
        Ok(Self(value))
    }
}

/// The version of an input contract or of an evaluator: 1 to 2,147,483,647.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "i64")]
pub struct Version(pub i64);

impl TryFrom<i64> for Version {
    type Error = String;

    fn try_from(value: i64) -> Result<Self, Self::Error> {
        if !(1..=MAX_VERSION).contains(&value) {
            return Err(format!("version must be between 1 and {MAX_VERSION}"));
        }
        Ok(Self(value))
    }
}

/// How long an attempt took, in milliseconds: 0 to 86,400,000, which is one
/// day.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "i64")]
pub struct DurationMs(pub i64);

impl TryFrom<i64> for DurationMs {
    type Error = String;

    fn try_from(value: i64) -> Result<Self, Self::Error> {
        if !(0..=MAX_DURATION_MS).contains(&value) {
            return Err(format!(
                "duration_ms must be between 0 and {MAX_DURATION_MS}"
            ));
        }
        Ok(Self(value))
    }
}

/// Any JSON value.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(transparent)]
pub struct JsonValue(pub Value);

/// Arbitrary JSON a caller sends, held as the canonical text Studio stores:
/// object names sorted, no insignificant whitespace, and at most 16,384
/// bytes. Two documents are the same content when their canonical text is
/// equal.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(try_from = "Value")]
pub struct CanonicalJson(pub String);

impl TryFrom<Value> for CanonicalJson {
    type Error = String;

    fn try_from(mut value: Value) -> Result<Self, Self::Error> {
        value.sort_all_objects();
        let text = value.to_string();
        if text.len() > MAX_JSON_BYTES {
            return Err(format!(
                "serialized JSON must be at most {MAX_JSON_BYTES} UTF-8 bytes"
            ));
        }
        Ok(Self(text))
    }
}

/// Whether a dataset still accepts cases.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum DatasetStatus {
    Draft,
    Locked,
}

/// How a case came to exist.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum CaseOrigin {
    Authored,
    Generated,
}

impl CaseOrigin {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Authored => "authored",
            Self::Generated => "generated",
        }
    }
}

/// The kind of application target a case runs.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum TargetKind {
    Node,
    Workflow,
    Agent,
}

impl TargetKind {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Node => "node",
            Self::Workflow => "workflow",
            Self::Agent => "agent",
        }
    }
}

/// Whether a run still has queued attempts.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum RunStatus {
    Active,
    Completed,
}

/// Where an attempt stands. Every status but `queued` is terminal.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum AttemptStatus {
    Queued,
    Passed,
    Failed,
    Error,
}

impl AttemptStatus {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Queued => "queued",
            Self::Passed => "passed",
            Self::Failed => "failed",
            Self::Error => "error",
        }
    }
}

/// The result a caller records for an attempt.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum TerminalAttemptStatus {
    Passed,
    Failed,
    Error,
}

impl From<TerminalAttemptStatus> for AttemptStatus {
    fn from(status: TerminalAttemptStatus) -> Self {
        match status {
            TerminalAttemptStatus::Passed => Self::Passed,
            TerminalAttemptStatus::Failed => Self::Failed,
            TerminalAttemptStatus::Error => Self::Error,
        }
    }
}

/// How a record uses an execution's evidence.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum EvidenceMembershipRole {
    /// A case was generated from the execution.
    CaseSource,
    /// The execution is what an attempt evaluated.
    AttemptSubject,
}

impl EvidenceMembershipRole {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::CaseSource => "case_source",
            Self::AttemptSubject => "attempt_subject",
        }
    }
}

/// The kind of evidence reference a membership lookup names.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum EvidenceKind {
    JunjoExecution,
    OtelSpan,
}

/// The discriminator value of a semantic execution reference.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[schema(default = "junjo_execution")]
pub enum SemanticExecutionKind {
    #[serde(rename = "junjo_execution")]
    JunjoExecution,
}

/// The discriminator value of an OpenTelemetry span reference.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[schema(default = "otel_span")]
pub enum OpenTelemetrySpanKind {
    #[serde(rename = "otel_span")]
    OtelSpan,
}

/// One Junjo execution, named by its service, executable type, and runtime
/// identity.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SemanticExecutionReference {
    #[schema(inline, required = false)]
    pub kind: SemanticExecutionKind,
    /// Exact normalized service.namespace; empty is explicit
    #[schema(value_type = String, max_length = 256, examples("junjo.examples"))]
    pub service_namespace: ServiceNamespaceText,
    #[schema(value_type = String, min_length = 1, max_length = 256, examples("ai-chat-evaluation"))]
    pub service_name: ExecutionIdentityText,
    #[schema(inline)]
    pub executable_type: ExecutableType,
    #[schema(value_type = String, min_length = 1, max_length = 256, examples("workflowRun123"))]
    pub runtime_id: ExecutionIdentityText,
}

/// One span of any OpenTelemetry producer, named by its service, trace, and
/// span identifier.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct OpenTelemetrySpanReference {
    #[schema(inline, required = false)]
    pub kind: OpenTelemetrySpanKind,
    /// Exact normalized service.namespace; empty is explicit
    #[schema(value_type = String, max_length = 256, examples("junjo.examples"))]
    pub service_namespace: ServiceNamespaceText,
    #[schema(value_type = String, min_length = 1, max_length = 256, examples("openai-agents-example"))]
    pub service_name: ExecutionIdentityText,
    #[schema(value_type = String, pattern = "^[0-9a-f]{32}$")]
    pub trace_id: TraceId,
    #[schema(value_type = String, pattern = "^[0-9a-f]{16}$")]
    pub span_id: SpanId,
}

/// The evidence of one execution, discriminated by `kind`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(untagged)]
#[schema(discriminator(property_name = "kind", mapping(
    ("junjo_execution" = "#/components/schemas/SemanticExecutionReference"),
    ("otel_span" = "#/components/schemas/OpenTelemetrySpanReference"),
)))]
pub enum ExecutionEvidenceReference {
    JunjoExecution(SemanticExecutionReference),
    OtelSpan(OpenTelemetrySpanReference),
}

/// Reads `kind` first and then the reference it names, so a caller is told
/// what is wrong with that reference.
impl<'de> Deserialize<'de> for ExecutionEvidenceReference {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let value = Value::deserialize(deserializer)?;
        let reference = match value.get("kind").and_then(Value::as_str) {
            Some("junjo_execution") => serde_json::from_value(value).map(Self::JunjoExecution),
            Some("otel_span") => serde_json::from_value(value).map(Self::OtelSpan),
            _ => {
                return Err(D::Error::custom(
                    "kind must be junjo_execution or otel_span",
                ));
            }
        };
        reference.map_err(D::Error::custom)
    }
}

/// The request to create a dataset.
#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationDatasetCreate {
    #[schema(value_type = String, min_length = 1, max_length = 128, examples("ai_chat"))]
    pub application_key: KeyText,
    #[schema(value_type = String, min_length = 1, max_length = 128, examples("local_place_realism_v1"))]
    pub key: KeyText,
    #[schema(value_type = String, min_length = 1, max_length = 256, examples("Local place realism"))]
    pub name: NameText,
    #[schema(value_type = Option<String>, max_length = 2048)]
    pub description: Option<DescriptionText>,
}

/// What a run listing says about a run's dataset.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationDatasetSummary {
    #[schema(min_length = 1, max_length = 64)]
    pub id: String,
    #[schema(min_length = 1, max_length = 128)]
    pub application_key: String,
    #[schema(min_length = 1, max_length = 128)]
    pub key: String,
    #[schema(min_length = 1, max_length = 256)]
    pub name: String,
    #[schema(inline)]
    pub status: DatasetStatus,
}

/// One dataset.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationDatasetRead {
    #[schema(min_length = 1, max_length = 64)]
    pub id: String,
    #[schema(min_length = 1, max_length = 128)]
    pub application_key: String,
    #[schema(min_length = 1, max_length = 128)]
    pub key: String,
    #[schema(min_length = 1, max_length = 256)]
    pub name: String,
    #[schema(inline)]
    pub status: DatasetStatus,
    #[schema(required, max_length = 2048)]
    pub description: Option<String>,
    /// The user who created the dataset. Null once that user is deleted.
    #[schema(required, min_length = 1, max_length = 64)]
    pub created_by_user_id: Option<String>,
    #[schema(value_type = String, format = DateTime)]
    pub created_at: UtcSeconds,
    #[schema(value_type = Option<String>, format = DateTime, required)]
    pub locked_at: Option<UtcSeconds>,
}

/// The request to add a case to a draft dataset.
#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationCaseCreate {
    #[schema(value_type = String, min_length = 1, max_length = 128, examples("specific_place_1"))]
    pub case_key: KeyText,
    #[schema(value_type = String, min_length = 1, max_length = 256, examples("Response place realism"))]
    pub evaluation_name: NameText,
    #[schema(inline)]
    pub origin: CaseOrigin,
    #[schema(inline)]
    pub target_kind: TargetKind,
    #[schema(value_type = String, min_length = 1, max_length = 128, examples("date_response_node"))]
    pub target_key: KeyText,
    #[schema(value_type = String, min_length = 1, max_length = 256, examples("CreateDateIdeaResponseNode"))]
    pub target_name: NameText,
    #[schema(value_type = i64, minimum = 1, maximum = 2147483647)]
    pub input_version: Version,
    #[schema(value_type = JsonValue)]
    pub input_json: CanonicalJson,
    #[schema(value_type = Option<JsonValue>)]
    pub expectation_json: Option<CanonicalJson>,
    #[schema(value_type = String, min_length = 1, max_length = 128, examples("response_quality"))]
    pub evaluator_key: KeyText,
    #[schema(value_type = i64, minimum = 1, maximum = 2147483647)]
    pub evaluator_version: Version,
    #[schema(inline)]
    pub source_evidence: Option<ExecutionEvidenceReference>,
    #[schema(value_type = Option<String>, pattern = "^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
    pub source_revision: Option<SourceRevision>,
}

impl EvaluationCaseCreate {
    /// An authored case names no source. A generated case names both the
    /// evidence and the revision it was generated from.
    pub fn validate_source_provenance(&self) -> Result<(), &'static str> {
        let has_evidence = self.source_evidence.is_some();
        let has_revision = self.source_revision.is_some();
        match self.origin {
            CaseOrigin::Authored if has_evidence || has_revision => {
                Err("authored cases cannot include source provenance")
            }
            CaseOrigin::Generated if !has_evidence || !has_revision => {
                Err("generated cases require both source_evidence and source_revision")
            }
            _ => Ok(()),
        }
    }
}

/// One case of a dataset.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationCaseRead {
    #[schema(min_length = 1, max_length = 64)]
    pub id: String,
    #[schema(min_length = 1, max_length = 64)]
    pub dataset_id: String,
    #[schema(min_length = 1, max_length = 128)]
    pub case_key: String,
    #[schema(min_length = 1, max_length = 256)]
    pub evaluation_name: String,
    /// The case's place in its dataset, counted from 1.
    #[schema(minimum = 1)]
    pub ordinal: i64,
    #[schema(inline)]
    pub origin: CaseOrigin,
    #[schema(inline)]
    pub target_kind: TargetKind,
    #[schema(min_length = 1, max_length = 128)]
    pub target_key: String,
    #[schema(min_length = 1, max_length = 256)]
    pub target_name: String,
    #[schema(minimum = 1, maximum = 2147483647)]
    pub input_version: i64,
    pub input_json: JsonValue,
    #[schema(required)]
    pub expectation_json: Option<JsonValue>,
    #[schema(min_length = 1, max_length = 128)]
    pub evaluator_key: String,
    #[schema(minimum = 1, maximum = 2147483647)]
    pub evaluator_version: i64,
    #[schema(required, inline)]
    pub source_evidence: Option<ExecutionEvidenceReference>,
    #[schema(required, pattern = "^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
    pub source_revision: Option<String>,
    #[schema(value_type = String, format = DateTime)]
    pub created_at: UtcSeconds,
}

/// One dataset with its cases in order.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationDatasetDetail {
    pub dataset: EvaluationDatasetRead,
    #[schema(max_items = 100)]
    pub cases: Vec<EvaluationCaseRead>,
}

/// One page of datasets, newest first.
#[derive(Debug, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationDatasetList {
    #[schema(max_items = 100)]
    pub items: Vec<EvaluationDatasetRead>,
    /// Send this as `cursor` to read the next page. Null on the last page.
    #[schema(required)]
    pub next_cursor: Option<String>,
}

/// The request to start a run of a locked dataset.
#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationRunStart {
    #[schema(value_type = String, min_length = 1, max_length = 64)]
    pub dataset_id: RecordId,
    /// Names this run within its dataset. Repeating a request returns the
    /// run it started.
    #[schema(value_type = String, min_length = 1, max_length = 128, examples("baseline-20260727"))]
    pub request_key: KeyText,
    #[schema(value_type = String, min_length = 1, max_length = 256, examples("baseline"))]
    pub run_label: NameText,
    #[schema(value_type = String, pattern = "^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
    pub source_revision: SourceRevision,
}

/// One run.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationRunRead {
    #[schema(min_length = 1, max_length = 64)]
    pub id: String,
    #[schema(min_length = 1, max_length = 64)]
    pub dataset_id: String,
    #[schema(min_length = 1, max_length = 128)]
    pub request_key: String,
    #[schema(min_length = 1, max_length = 256)]
    pub run_label: String,
    #[schema(pattern = "^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
    pub source_revision: String,
    #[schema(inline)]
    pub status: RunStatus,
    /// The user who started the run. Null once that user is deleted.
    #[schema(required, min_length = 1, max_length = 64)]
    pub created_by_user_id: Option<String>,
    #[schema(value_type = String, format = DateTime)]
    pub created_at: UtcSeconds,
    #[schema(value_type = Option<String>, format = DateTime, required)]
    pub completed_at: Option<UtcSeconds>,
}

/// One case's attempt in one run.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationAttemptRead {
    #[schema(min_length = 1, max_length = 64)]
    pub id: String,
    #[schema(min_length = 1, max_length = 64)]
    pub run_id: String,
    #[schema(min_length = 1, max_length = 64)]
    pub case_id: String,
    #[schema(inline)]
    pub status: AttemptStatus,
    #[schema(required, min_length = 1, max_length = 4096)]
    pub reason: Option<String>,
    #[schema(minimum = 0, maximum = 86400000)]
    pub duration_ms: Option<i64>,
    /// The execution this attempt evaluated.
    #[schema(required, inline)]
    pub subject_evidence: Option<ExecutionEvidenceReference>,
    #[schema(value_type = Option<String>, format = DateTime, required)]
    pub evidence_bound_at: Option<UtcSeconds>,
    #[schema(value_type = Option<String>, format = DateTime, required)]
    pub recorded_at: Option<UtcSeconds>,
}

/// One case of a run with its attempt.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationRunCase {
    pub case: EvaluationCaseRead,
    pub attempt: EvaluationAttemptRead,
}

/// One run with its dataset and every case's attempt, in case order.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationRunDetail {
    pub run: EvaluationRunRead,
    pub dataset: EvaluationDatasetRead,
    #[schema(max_items = 100)]
    pub cases: Vec<EvaluationRunCase>,
}

/// One attempt with its run, dataset, and case.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationAttemptDetail {
    pub run: EvaluationRunRead,
    pub dataset: EvaluationDatasetRead,
    pub case: EvaluationCaseRead,
    pub attempt: EvaluationAttemptRead,
}

/// The exact, conjunctive case scope applied to a run-list projection.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationRunScope {
    #[schema(value_type = Option<String>, min_length = 1, max_length = 64)]
    pub dataset_id: Option<RecordId>,
    #[schema(inline)]
    pub target_kind: Option<TargetKind>,
    #[schema(value_type = Option<String>, min_length = 1, max_length = 128)]
    pub target_key: Option<KeyText>,
    #[schema(value_type = Option<i64>, minimum = 1, maximum = 2147483647)]
    pub input_version: Option<Version>,
    #[schema(value_type = Option<String>, min_length = 1, max_length = 256)]
    pub evaluation_name: Option<NameText>,
}

/// Bounded outcome aggregates for the attempts visible in one scope.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationOutcomeSummary {
    #[schema(minimum = 0, maximum = 100)]
    pub total: i64,
    #[schema(minimum = 0, maximum = 100)]
    pub queued: i64,
    /// The attempts that passed or failed.
    #[schema(minimum = 0, maximum = 100)]
    pub judged: i64,
    #[schema(minimum = 0, maximum = 100)]
    pub passed: i64,
    #[schema(minimum = 0, maximum = 100)]
    pub failed: i64,
    #[schema(minimum = 0, maximum = 100)]
    pub error: i64,
    /// The share of judged attempts that passed. Null when none is judged.
    #[schema(minimum = 0.0, maximum = 1.0)]
    pub pass_rate: Option<f64>,
    /// The share of attempts that are judged. Null when there is none.
    #[schema(minimum = 0.0, maximum = 1.0)]
    pub coverage: Option<f64>,
}

/// How many cases of a dataset run one target at one input version.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationTargetFacet {
    #[schema(inline)]
    pub target_kind: TargetKind,
    #[schema(min_length = 1, max_length = 128)]
    pub target_key: String,
    #[schema(min_length = 1, max_length = 256)]
    pub target_name: String,
    #[schema(minimum = 1, maximum = 2147483647)]
    pub input_version: i64,
    #[schema(minimum = 1, maximum = 100)]
    pub case_count: i64,
}

/// How many cases of a dataset share one evaluation name.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationNameFacet {
    #[schema(min_length = 1, max_length = 256)]
    pub evaluation_name: String,
    #[schema(minimum = 1, maximum = 100)]
    pub case_count: i64,
}

/// One run in a listing: its outcomes within the scope, and the facets of
/// its whole dataset.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationRunSummary {
    pub run: EvaluationRunRead,
    pub dataset: EvaluationDatasetSummary,
    pub outcome_summary: EvaluationOutcomeSummary,
    #[schema(max_items = 100)]
    pub target_facets: Vec<EvaluationTargetFacet>,
    #[schema(max_items = 100)]
    pub evaluation_facets: Vec<EvaluationNameFacet>,
}

/// One page of runs, newest first, with the scope that selected them.
#[derive(Debug, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationRunList {
    pub scope: EvaluationRunScope,
    #[schema(max_items = 100)]
    pub items: Vec<EvaluationRunSummary>,
    /// Send this as `cursor` to read the next page. Null on the last page.
    #[schema(required)]
    pub next_cursor: Option<String>,
}

/// The request to bind an attempt to the execution it evaluated.
#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationEvidenceBind {
    #[schema(inline)]
    pub evidence: ExecutionEvidenceReference,
}

/// The request to record an attempt's result.
#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationAttemptResult {
    #[schema(inline)]
    pub status: TerminalAttemptStatus,
    #[schema(value_type = String, min_length = 1, max_length = 4096)]
    pub reason: ReasonText,
    #[schema(value_type = Option<i64>, minimum = 0, maximum = 86400000)]
    pub duration_ms: Option<DurationMs>,
}

/// One record that uses an execution's evidence. A case source names no run
/// and no attempt. An attempt subject names both.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationEvidenceMembership {
    #[schema(inline)]
    pub role: EvidenceMembershipRole,
    #[schema(min_length = 1, max_length = 64)]
    pub dataset_id: String,
    #[schema(min_length = 1, max_length = 64)]
    pub case_id: String,
    #[schema(required, min_length = 1, max_length = 64)]
    pub run_id: Option<String>,
    #[schema(required, min_length = 1, max_length = 64)]
    pub attempt_id: Option<String>,
}

/// One page of the records that use an execution's evidence.
#[derive(Debug, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationEvidenceMembershipList {
    #[schema(max_items = 100)]
    pub items: Vec<EvaluationEvidenceMembership>,
    /// Send this as `cursor` to read the next page. Null on the last page.
    #[schema(required)]
    pub next_cursor: Option<String>,
}

/// The body of a conflict response. `code` names the conflict. It describes
/// what `ApiError::conflict` builds and is never constructed.
#[allow(dead_code)]
#[derive(Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvaluationConflictResponse {
    code: String,
    message: String,
}
