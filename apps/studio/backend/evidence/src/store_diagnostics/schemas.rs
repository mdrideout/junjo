//! Typed projections shared by Workflow and Agent Store diagnostics.

use serde::Serialize;
use utoipa::ToSchema;

use crate::json::Json;

/// How one payload slot was emitted, or that it is forensically absent.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum PayloadMode {
    Full,
    Redacted,
    Excluded,
    Reference,
    Missing,
}

impl PayloadMode {
    /// The modes a producer may emit. `Missing` is assigned only here.
    pub const EMITTED: [&'static str; 4] = ["full", "redacted", "excluded", "reference"];

    pub fn from_emitted(mode: &str) -> Option<Self> {
        match mode {
            "full" => Some(Self::Full),
            "redacted" => Some(Self::Redacted),
            "excluded" => Some(Self::Excluded),
            "reference" => Some(Self::Reference),
            _ => None,
        }
    }

    /// Inline content exists and can be inspected or replayed.
    pub fn is_inline(self) -> bool {
        matches!(self, Self::Full | Self::Redacted)
    }
}

/// One emitted payload slot or explicit forensic absence.
///
/// `value` is JSON null both when the payload is the JSON value null and when
/// the slot carries no inline content. `mode` keeps the two unambiguous.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PayloadEvidence {
    #[schema(inline)]
    pub mode: PayloadMode,
    #[schema(min_length = 1)]
    pub policy: Option<String>,
    #[schema(required = false)]
    pub value: Json,
    #[schema(min_length = 1)]
    pub reference: Option<String>,
    #[schema(min_length = 1)]
    pub reason: Option<String>,
}

/// Stable machine-readable evidence problem.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvidenceDiagnostic {
    #[schema(min_length = 1)]
    pub code: String,
    #[schema(min_length = 1)]
    pub path: String,
    #[schema(min_length = 1)]
    pub message: String,
}

impl EvidenceDiagnostic {
    /// Build a diagnostic whose three members are never empty.
    pub fn new(
        code: impl Into<String>,
        path: impl Into<String>,
        message: impl Into<String>,
    ) -> Self {
        Self {
            code: nonempty(code.into(), "invalid_evidence"),
            path: nonempty(path.into(), "evidence"),
            message: nonempty(
                message.into(),
                "Evidence contains nonportable diagnostic text.",
            ),
        }
    }
}

fn nonempty(text: String, fallback: &str) -> String {
    if text.is_empty() {
        fallback.to_string()
    } else {
        text
    }
}

/// Preserved OTLP loss counters relevant to one semantic projection.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvidenceLossCounts {
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub resource_dropped_attributes: i64,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub span_dropped_attributes: i64,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub span_dropped_events: i64,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub span_dropped_links: i64,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub event_dropped_attributes: i64,
}

impl EvidenceLossCounts {
    pub fn any_loss(&self) -> bool {
        [
            self.resource_dropped_attributes,
            self.span_dropped_attributes,
            self.span_dropped_events,
            self.span_dropped_links,
            self.event_dropped_attributes,
        ]
        .iter()
        .any(|count| *count > 0)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum IntegrityStatus {
    Complete,
    Partial,
}

/// Backend-owned verdict for required semantic evidence.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EvidenceIntegrity {
    #[schema(inline)]
    pub status: IntegrityStatus,
    pub diagnostics: Vec<EvidenceDiagnostic>,
    pub loss_counts: EvidenceLossCounts,
}

impl EvidenceIntegrity {
    /// Evidence is complete only with no diagnostics and no recorded loss.
    pub fn new(diagnostics: Vec<EvidenceDiagnostic>, loss_counts: EvidenceLossCounts) -> Self {
        let status = if diagnostics.is_empty() && !loss_counts.any_loss() {
            IntegrityStatus::Complete
        } else {
            IntegrityStatus::Partial
        };
        Self {
            status,
            diagnostics,
            loss_counts,
        }
    }
}

/// One ordered Store transition and its verified projections.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct StoreTransition {
    #[schema(minimum = 1, maximum = 9007199254740991_i64)]
    pub sequence: i64,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub revision_before: i64,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub revision_after: i64,
    #[schema(pattern = "^[0-9a-f]{16}$")]
    pub span_id: String,
    #[schema(min_length = 1)]
    pub event_id: String,
    #[schema(min_length = 1)]
    pub action: String,
    pub patch: PayloadEvidence,
    #[schema(required = false)]
    pub before: Json,
    #[schema(required = false)]
    pub after: Json,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ReconstructionStatus {
    Verified,
    PolicyUnavailable,
    Failed,
    NotApplicable,
}

/// Execution interval on a Store, independent of its shared transition log.
///
/// The interval is the transitions after `sequence_start`, up to and
/// including `sequence_end`.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct StoreBoundaryDetail {
    pub available: bool,
    #[schema(min_length = 1)]
    pub store_id: Option<String>,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub sequence_start: Option<i64>,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub sequence_end: Option<i64>,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub revision_start: Option<i64>,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub revision_end: Option<i64>,
    #[schema(
        required = false,
        default = 0,
        minimum = 0,
        maximum = 9007199254740991_i64
    )]
    pub transition_count: i64,
    #[schema(required = false, default = false)]
    pub reconstructable_claimed: bool,
    pub reconstructable: bool,
    #[schema(inline)]
    pub reconstruction_status: ReconstructionStatus,
    #[schema(min_length = 1)]
    pub reconstruction_reason: Option<String>,
    pub start: Option<PayloadEvidence>,
    pub end: Option<PayloadEvidence>,
}

impl StoreBoundaryDetail {
    /// This boundary with the transitions in its interval.
    pub fn with_transitions(self, transitions: Vec<StoreTransition>) -> StoreDetail {
        StoreDetail {
            available: self.available,
            store_id: self.store_id,
            sequence_start: self.sequence_start,
            sequence_end: self.sequence_end,
            revision_start: self.revision_start,
            revision_end: self.revision_end,
            transition_count: self.transition_count,
            reconstructable_claimed: self.reconstructable_claimed,
            reconstructable: self.reconstructable,
            reconstruction_status: self.reconstruction_status,
            reconstruction_reason: self.reconstruction_reason,
            start: self.start,
            end: self.end,
            transitions,
        }
    }
}

/// An execution boundary hydrated with the transitions in its interval.
///
/// Its members are those of `StoreBoundaryDetail`, then the transitions.
#[derive(Debug, Clone, PartialEq, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct StoreDetail {
    pub available: bool,
    #[schema(min_length = 1)]
    pub store_id: Option<String>,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub sequence_start: Option<i64>,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub sequence_end: Option<i64>,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub revision_start: Option<i64>,
    #[schema(minimum = 0, maximum = 9007199254740991_i64)]
    pub revision_end: Option<i64>,
    #[schema(
        required = false,
        default = 0,
        minimum = 0,
        maximum = 9007199254740991_i64
    )]
    pub transition_count: i64,
    #[schema(required = false, default = false)]
    pub reconstructable_claimed: bool,
    pub reconstructable: bool,
    #[schema(inline)]
    pub reconstruction_status: ReconstructionStatus,
    #[schema(min_length = 1)]
    pub reconstruction_reason: Option<String>,
    pub start: Option<PayloadEvidence>,
    pub end: Option<PayloadEvidence>,
    #[schema(required = false)]
    pub transitions: Vec<StoreTransition>,
}

impl StoreDetail {
    /// A Store that does not apply to this executable, with the reason.
    pub fn unavailable(reason: &str) -> Self {
        Self {
            available: false,
            store_id: None,
            sequence_start: None,
            sequence_end: None,
            revision_start: None,
            revision_end: None,
            transition_count: 0,
            reconstructable_claimed: false,
            reconstructable: false,
            reconstruction_status: ReconstructionStatus::NotApplicable,
            reconstruction_reason: Some(reason.to_string()),
            start: None,
            end: None,
            transitions: Vec::new(),
        }
    }

    /// The boundary alone, and the transitions it was hydrated with.
    pub fn into_boundary(self) -> (StoreBoundaryDetail, Vec<StoreTransition>) {
        let boundary = StoreBoundaryDetail {
            available: self.available,
            store_id: self.store_id,
            sequence_start: self.sequence_start,
            sequence_end: self.sequence_end,
            revision_start: self.revision_start,
            revision_end: self.revision_end,
            transition_count: self.transition_count,
            reconstructable_claimed: self.reconstructable_claimed,
            reconstructable: self.reconstructable,
            reconstruction_status: self.reconstruction_status,
            reconstruction_reason: self.reconstruction_reason,
            start: self.start,
            end: self.end,
        };
        (boundary, self.transitions)
    }
}
