"""Strict data contracts for Junjo AI Studio evaluation APIs.

These models mirror Studio's versioned REST contract without importing Studio
runtime code.  They are immutable so a request or response cannot silently
change after validation, and every object rejects unknown fields.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

MAX_CASES_PER_DATASET = 100
MAX_PAGE_SIZE = 100
MAX_CURSOR_BYTES = 1_024
MAX_JSON_BYTES = 16_384
MAX_KEY_BYTES = 128
MAX_NAME_BYTES = 256
MAX_DESCRIPTION_BYTES = 2_048
MAX_REASON_BYTES = 4_096
MAX_EXECUTION_IDENTITY_BYTES = 256
MAX_RECORD_ID_BYTES = 64
MAX_DURATION_MS = 86_400_000
MAX_VERSION = 2_147_483_647

JsonObject = dict[str, JsonValue]


def _validate_text(
    value: str,
    *,
    field_name: str,
    max_bytes: int,
    nonempty: bool,
) -> str:
    if nonempty and not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ValueError(f"{field_name} must contain valid Unicode text") from error
    if len(encoded) > max_bytes:
        raise ValueError(f"{field_name} must be at most {max_bytes} UTF-8 bytes")
    return value


def _validate_key(value: str) -> str:
    return _validate_text(
        value,
        field_name="key",
        max_bytes=MAX_KEY_BYTES,
        nonempty=True,
    )


def _validate_name(value: str) -> str:
    return _validate_text(
        value,
        field_name="name",
        max_bytes=MAX_NAME_BYTES,
        nonempty=True,
    )


def _validate_description(value: str) -> str:
    return _validate_text(
        value,
        field_name="description",
        max_bytes=MAX_DESCRIPTION_BYTES,
        nonempty=False,
    )


def _validate_reason(value: str) -> str:
    return _validate_text(
        value,
        field_name="reason",
        max_bytes=MAX_REASON_BYTES,
        nonempty=True,
    )


def _validate_service_namespace(value: str) -> str:
    return _validate_text(
        value,
        field_name="service_namespace",
        max_bytes=MAX_EXECUTION_IDENTITY_BYTES,
        nonempty=False,
    )


def _validate_execution_identity(value: str) -> str:
    return _validate_text(
        value,
        field_name="execution identity",
        max_bytes=MAX_EXECUTION_IDENTITY_BYTES,
        nonempty=True,
    )


def _validate_cursor(value: str) -> str:
    return _validate_text(
        value,
        field_name="cursor",
        max_bytes=MAX_CURSOR_BYTES,
        nonempty=True,
    )


KeyText = Annotated[
    str,
    Field(min_length=1, max_length=MAX_KEY_BYTES),
    AfterValidator(_validate_key),
]
NameText = Annotated[
    str,
    Field(min_length=1, max_length=MAX_NAME_BYTES),
    AfterValidator(_validate_name),
]
DescriptionText = Annotated[
    str,
    Field(max_length=MAX_DESCRIPTION_BYTES),
    AfterValidator(_validate_description),
]
ReasonText = Annotated[
    str,
    Field(min_length=1, max_length=MAX_REASON_BYTES),
    AfterValidator(_validate_reason),
]
ServiceNamespaceText = Annotated[
    str,
    Field(max_length=MAX_EXECUTION_IDENTITY_BYTES),
    AfterValidator(_validate_service_namespace),
]
ExecutionIdentityText = Annotated[
    str,
    Field(min_length=1, max_length=MAX_EXECUTION_IDENTITY_BYTES),
    AfterValidator(_validate_execution_identity),
]
SourceRevision = Annotated[
    str,
    Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$"),
]
CursorText = Annotated[
    str,
    Field(min_length=1, max_length=MAX_CURSOR_BYTES),
    AfterValidator(_validate_cursor),
]
RecordId = Annotated[
    str,
    Field(min_length=1, max_length=MAX_RECORD_ID_BYTES),
]
TraceId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
SpanId = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]


def dump_bounded_json(value: JsonValue) -> str:
    """Serialize a JSON value deterministically and enforce Studio's byte cap.

    :param value: Portable JSON value to validate.
    :return: Canonical compact JSON used for byte-size validation.
    :raises ValueError: If the value is not interoperable JSON or is too large.
    """

    try:
        serialized = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        encoded = serialized.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise ValueError("value must be interoperable JSON") from error
    if len(encoded) > MAX_JSON_BYTES:
        raise ValueError(f"serialized JSON must be at most {MAX_JSON_BYTES} UTF-8 bytes")
    return serialized


class StudioDto(BaseModel):
    """Immutable closed base contract for values exchanged with Studio."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class StudioHealth(StudioDto):
    """Studio product identity returned by its public health endpoint."""

    status: str = Field(min_length=1)
    """Health status reported by the Studio backend."""
    version: str = Field(min_length=1)
    """Backend application version reported by Studio."""
    app_name: str = Field(min_length=1)
    """Backend application name reported by Studio."""


class DatasetStatus(StrEnum):
    """Lifecycle state of a Studio evaluation dataset."""

    DRAFT = "draft"
    LOCKED = "locked"


class CaseOrigin(StrEnum):
    """How an evaluation case entered a dataset."""

    AUTHORED = "authored"
    GENERATED = "generated"


class TargetKind(StrEnum):
    """Junjo execution shape selected by an evaluation case."""

    NODE = "node"
    WORKFLOW = "workflow"
    AGENT = "agent"


class ExecutableType(StrEnum):
    """Semantic execution types that Studio can resolve to trace evidence."""

    WORKFLOW = "workflow"
    SUBFLOW = "subflow"
    AGENT = "agent"


class RunStatus(StrEnum):
    """Aggregate lifecycle state of an evaluation run."""

    ACTIVE = "active"
    COMPLETED = "completed"


class AttemptStatus(StrEnum):
    """Lifecycle or terminal result of one case attempt."""

    QUEUED = "queued"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


TERMINAL_ATTEMPT_STATUSES = frozenset(
    {
        AttemptStatus.PASSED,
        AttemptStatus.FAILED,
        AttemptStatus.ERROR,
    }
)


class SemanticExecutionReference(StudioDto):
    """Exact ADR 0007 identity used to resolve received execution evidence."""

    kind: Literal["junjo_execution"] = "junjo_execution"
    """Discriminator for native Junjo semantic execution references."""
    service_namespace: ServiceNamespaceText = Field(
        description="Exact normalized service.namespace; empty is explicit",
    )
    """OpenTelemetry service.namespace used to disambiguate execution identity."""
    service_name: ExecutionIdentityText
    """OpenTelemetry service.name emitted by the application that owns the execution."""
    executable_type: ExecutableType
    """Native executable kind: workflow, subflow, or agent."""
    runtime_id: ExecutionIdentityText
    """Per-invocation native execution identity; combine it with service identity and executable type."""


class OpenTelemetrySpanReference(StudioDto):
    """Exact OpenTelemetry span identity used for external execution evidence."""

    kind: Literal["otel_span"] = "otel_span"
    """Discriminator for an exact OpenTelemetry trace/span reference."""
    service_namespace: ServiceNamespaceText = Field(
        description="Exact normalized service.namespace; empty is explicit",
    )
    """OpenTelemetry service.namespace used to disambiguate execution identity."""
    service_name: ExecutionIdentityText
    """OpenTelemetry service.name emitted by the application that owns the execution."""
    trace_id: TraceId
    """OpenTelemetry trace identifier linking the complete recorded chronology."""
    span_id: SpanId
    """OpenTelemetry span identifier within the selected trace."""


ExecutionEvidenceReference = Annotated[
    SemanticExecutionReference | OpenTelemetrySpanReference,
    Field(discriminator="kind"),
]


class DatasetCreate(StudioDto):
    """Request to create an idempotently keyed evaluation dataset."""

    application_key: KeyText
    """Application-owned namespace that groups datasets for one evaluation harness."""
    key: KeyText
    """Application-owned dataset key; reused with the same application key for idempotent creation."""
    name: NameText
    """Human-readable name retained with this record."""
    description: DescriptionText | None = None
    """Optional explanation of the dataset purpose and scenario coverage."""


class DatasetSummary(StudioDto):
    """Bounded dataset projection embedded in run-list responses."""

    id: RecordId
    """Studio-assigned dataset identifier used by dataset and run operations."""
    application_key: KeyText
    """Application-owned namespace that groups datasets for one evaluation harness."""
    key: KeyText
    """Application-owned dataset key; reused with the same application key for idempotent creation."""
    name: NameText
    """Human-readable name retained with this record."""
    status: DatasetStatus
    """Draft permits case additions; locked permanently freezes the ordered cases."""


class DatasetRead(DatasetSummary):
    """Complete evaluation dataset control record."""

    description: DescriptionText | None
    """Optional explanation of the dataset purpose and scenario coverage."""
    created_by_user_id: RecordId | None
    """Studio user who created the record through an authenticated request."""
    created_at: datetime
    """Creation timestamp recorded by Studio."""
    locked_at: datetime | None
    """Timestamp of the permanent dataset lock; absent while the dataset is draft."""


class CaseCreate(StudioDto):
    """Request to append one immutable input case to a draft dataset."""

    case_key: KeyText
    """Application-owned case key, unique within its dataset and used for idempotent writes."""
    evaluation_name: NameText
    """Human-readable evaluation label used to group and filter scenarios."""
    origin: CaseOrigin
    """Whether the case was authored directly or generated by executing a real application target."""
    target_kind: TargetKind
    """Execution boundary: a node, workflow, or agent."""
    target_key: KeyText
    """Stable dispatch key matching a target registered in the application harness."""
    target_name: NameText
    """Recorded target display name; the runner checks it against the registered declaration."""
    input_version: int = Field(ge=1, le=MAX_VERSION)
    """Version of the target input contract used to validate the stored case."""
    input_json: JsonValue
    """Scenario input validated by the application target input schema before execution."""
    expectation_json: JsonValue | None = None
    """Evaluator criteria, not an automatically accepted generated answer; validated by the evaluator schema."""
    evaluator_key: KeyText
    """Stable key of the evaluator registered in the application harness."""
    evaluator_version: int = Field(ge=1, le=MAX_VERSION)
    """Evaluator contract version that interprets the stored expectations."""
    source_evidence: ExecutionEvidenceReference | None = None
    """Exact execution reference for a generated case; absent for authored cases."""
    source_revision: SourceRevision | None = None
    """Clean committed application Git revision associated with this execution."""

    @field_validator("input_json")
    @classmethod
    def validate_input_json_size(cls, value: JsonValue) -> JsonValue:
        """Enforce the Studio input payload bound before any network work."""

        dump_bounded_json(value)
        return value

    @field_validator("expectation_json")
    @classmethod
    def validate_expectation_json_size(cls, value: JsonValue | None) -> JsonValue | None:
        """Enforce the Studio expectation payload bound before network work."""

        if value is not None:
            dump_bounded_json(value)
        return value

    @model_validator(mode="after")
    def validate_source_provenance(self) -> CaseCreate:
        """Require exact provenance for generated cases and forbid it otherwise."""

        if self.origin is CaseOrigin.AUTHORED:
            if self.source_evidence is not None or self.source_revision is not None:
                raise ValueError("authored cases cannot include source provenance")
            return self
        if self.source_evidence is None or self.source_revision is None:
            raise ValueError("generated cases require both source_evidence and source_revision")
        return self


class CaseRead(StudioDto):
    """Immutable evaluation case returned by Studio."""

    id: RecordId
    """Studio-assigned case identifier, preserved across runs on this dataset."""
    dataset_id: RecordId
    """Studio identifier of the dataset containing the ordered cases."""
    case_key: KeyText
    """Application-owned case key, unique within its dataset and used for idempotent writes."""
    evaluation_name: NameText
    """Human-readable evaluation label used to group and filter scenarios."""
    ordinal: int = Field(ge=1)
    """Stored case order within the dataset, preserved when runs are compared."""
    origin: CaseOrigin
    """Whether the case was authored directly or generated by executing a real application target."""
    target_kind: TargetKind
    """Execution boundary: a node, workflow, or agent."""
    target_key: KeyText
    """Stable dispatch key matching a target registered in the application harness."""
    target_name: NameText
    """Recorded target display name; the runner checks it against the registered declaration."""
    input_version: int = Field(ge=1, le=MAX_VERSION)
    """Version of the target input contract used to validate the stored case."""
    input_json: JsonValue
    """Scenario input validated by the application target input schema before execution."""
    expectation_json: JsonValue | None
    """Evaluator criteria, not an automatically accepted generated answer; validated by the evaluator schema."""
    evaluator_key: KeyText
    """Stable key of the evaluator registered in the application harness."""
    evaluator_version: int = Field(ge=1, le=MAX_VERSION)
    """Evaluator contract version that interprets the stored expectations."""
    source_evidence: ExecutionEvidenceReference | None
    """Exact execution reference for a generated case; absent for authored cases."""
    source_revision: SourceRevision | None
    """Clean committed application Git revision associated with this execution."""
    created_at: datetime
    """Creation timestamp recorded by Studio."""


class DatasetDetail(StudioDto):
    """A dataset and its bounded, ordinal case membership."""

    dataset: DatasetRead
    """Dataset metadata, including its immutable identity and lock status."""
    cases: tuple[CaseRead, ...] = Field(max_length=MAX_CASES_PER_DATASET)
    """Complete ordered dataset membership; locking preserves this order for future runs."""


class DatasetList(StudioDto):
    """One bounded cursor page of evaluation datasets."""

    items: tuple[DatasetRead, ...] = Field(max_length=MAX_PAGE_SIZE)
    """Records in this response page; continue with next_cursor when present."""
    next_cursor: str | None
    """Opaque continuation token for the next page; None means there is no next page."""


class RunStart(StudioDto):
    """Request to create or retrieve one idempotently keyed labeled run."""

    dataset_id: RecordId
    """Studio identifier of the dataset containing the ordered cases."""
    request_key: KeyText
    """Caller-owned idempotency key for a run on this dataset; reuse it only to resume the same experiment."""
    run_label: NameText
    """Human-readable experiment label, such as baseline or candidate."""
    source_revision: SourceRevision
    """Clean committed application Git revision associated with this execution."""


class RunRead(StudioDto):
    """Evaluation run control record."""

    id: RecordId
    """Studio-assigned run identifier used for comparison and attempt discovery."""
    dataset_id: RecordId
    """Studio identifier of the dataset containing the ordered cases."""
    request_key: KeyText
    """Caller-owned idempotency key for a run on this dataset; reuse it only to resume the same experiment."""
    run_label: NameText
    """Human-readable experiment label, such as baseline or candidate."""
    source_revision: SourceRevision
    """Clean committed application Git revision associated with this execution."""
    status: RunStatus
    """Active while attempts remain queued; completed once every attempt is terminal."""
    created_by_user_id: RecordId | None
    """Studio user who created the record through an authenticated request."""
    created_at: datetime
    """Creation timestamp recorded by Studio."""
    completed_at: datetime | None
    """Timestamp when every attempt became terminal; absent for an active run."""


class AttemptRead(StudioDto):
    """One case attempt, including terminal judgment and execution binding."""

    id: RecordId
    """Studio-assigned attempt identifier used to retrieve outcomes and exact evidence."""
    run_id: RecordId
    """Studio identifier of the evaluation run."""
    case_id: RecordId
    """Studio identifier of the immutable case used by this attempt."""
    status: AttemptStatus
    """Queued, passed, failed, or error; operational errors are distinct from failed judgments."""
    reason: ReasonText | None
    """Recorded explanation of the judgment or operational error."""
    duration_ms: int | None = Field(
        default=None,
        ge=0,
        le=MAX_DURATION_MS,
    )
    """Measured subject execution duration in milliseconds; None means unavailable, not zero."""
    subject_evidence: ExecutionEvidenceReference | None
    """Exact target execution reference bound before the evaluator records its judgment."""
    evidence_bound_at: datetime | None
    """Timestamp when the attempt was linked to its subject execution."""
    recorded_at: datetime | None
    """Timestamp when a terminal result was recorded; absent for a queued attempt."""


class RunCaseRead(StudioDto):
    """A locked case paired with its attempt in one run."""

    case: CaseRead
    """The stored case, including input, evaluation criteria, and provenance."""
    attempt: AttemptRead
    """Attempt record for this case and run."""


class RunDetail(StudioDto):
    """A run, locked dataset, and complete bounded case-attempt membership."""

    run: RunRead
    """Run metadata, including source revision and lifecycle status."""
    dataset: DatasetRead
    """Dataset metadata, including its immutable identity and lock status."""
    cases: tuple[RunCaseRead, ...] = Field(max_length=MAX_CASES_PER_DATASET)
    """Ordered cases paired with the single attempt created for each case in this run."""


class AttemptDetail(StudioDto):
    """Self-contained control context for one attempt."""

    run: RunRead
    """Run metadata, including source revision and lifecycle status."""
    dataset: DatasetRead
    """Dataset metadata, including its immutable identity and lock status."""
    case: CaseRead
    """The stored case, including input, evaluation criteria, and provenance."""
    attempt: AttemptRead
    """Attempt record for this case and run."""


class RunScope(StudioDto):
    """The exact, conjunctive case scope applied to a run-list projection."""

    dataset_id: RecordId | None = None
    """Optional dataset filter; all non-null scope fields are combined with AND."""
    target_kind: TargetKind | None = None
    """Execution boundary: a node, workflow, or agent."""
    target_key: KeyText | None = None
    """Stable dispatch key matching a target registered in the application harness."""
    input_version: int | None = Field(default=None, ge=1, le=MAX_VERSION)
    """Version of the target input contract used to validate the stored case."""
    evaluation_name: NameText | None = None
    """Human-readable evaluation label used to group and filter scenarios."""


class OutcomeSummary(StudioDto):
    """Bounded outcome aggregates for the attempts visible in one scope."""

    total: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Total attempts in the selected scope, including queued attempts and errors."""
    queued: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Attempts that have not received a terminal result."""
    judged: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Attempts judged passed or failed; excludes queued attempts and operational errors."""
    passed: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Attempts satisfying the evaluator criteria."""
    failed: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Attempts that did not satisfy the evaluator criteria."""
    error: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    """Attempts whose target or evaluator could not complete successfully."""
    pass_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    """Passed divided by judged attempts, as a fraction from 0 to 1; None when nothing was judged."""
    coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    """Judged attempts divided by total attempts, as a fraction from 0 to 1; None when the scope has no attempts."""


class TargetFacet(StudioDto):
    """One target identity and its case count in a run's dataset."""

    target_kind: TargetKind
    """Execution boundary: a node, workflow, or agent."""
    target_key: KeyText
    """Stable dispatch key matching a target registered in the application harness."""
    target_name: NameText
    """Recorded target display name; the runner checks it against the registered declaration."""
    input_version: int = Field(ge=1, le=MAX_VERSION)
    """Version of the target input contract used to validate the stored case."""
    case_count: int = Field(ge=1, le=MAX_CASES_PER_DATASET)
    """Number of cases represented by this facet."""


class EvaluationNameFacet(StudioDto):
    """One human evaluation name and its case count in a run's dataset."""

    evaluation_name: NameText
    """Human-readable evaluation label used to group and filter scenarios."""
    case_count: int = Field(ge=1, le=MAX_CASES_PER_DATASET)
    """Number of cases represented by this facet."""


class RunSummary(StudioDto):
    """Bounded run-list projection."""

    run: RunRead
    """Run metadata, including source revision and lifecycle status."""
    dataset: DatasetSummary
    """Dataset metadata, including its immutable identity and lock status."""
    outcome_summary: OutcomeSummary
    """Pass, failure, error, and coverage totals for the selected run scope."""
    target_facets: tuple[TargetFacet, ...] = Field(max_length=MAX_CASES_PER_DATASET)
    """Distinct target identities represented by cases in the run."""
    evaluation_facets: tuple[EvaluationNameFacet, ...] = Field(max_length=MAX_CASES_PER_DATASET)
    """Evaluation labels and their case counts within the run."""


class RunList(StudioDto):
    """One bounded cursor page of evaluation runs."""

    scope: RunScope
    """Effective conjunctive case filters applied to this run listing."""
    items: tuple[RunSummary, ...] = Field(max_length=MAX_PAGE_SIZE)
    """Records in this response page; continue with next_cursor when present."""
    next_cursor: str | None
    """Opaque continuation token for the next page; None means there is no next page."""


class EvidenceMembershipItem(StudioDto):
    """One exact case-source or attempt-subject membership."""

    role: Literal["case_source", "attempt_subject"]
    """Whether the execution supplied a generated case or was the subject of an evaluation attempt."""
    dataset_id: RecordId
    """Studio identifier of the dataset containing the ordered cases."""
    case_id: RecordId
    """Studio identifier of the immutable case used by this attempt."""
    run_id: RecordId | None
    """Studio identifier of the evaluation run."""
    attempt_id: RecordId | None
    """Studio identifier of one case attempt within an evaluation run."""

    @model_validator(mode="after")
    def validate_role_identity(self) -> EvidenceMembershipItem:
        """Keep source and subject membership identities coherent."""

        if self.role == "case_source":
            if self.run_id is not None or self.attempt_id is not None:
                raise ValueError("case_source membership cannot include run or attempt IDs")
        elif self.run_id is None or self.attempt_id is None:
            raise ValueError("attempt_subject membership requires run and attempt IDs")
        return self


class EvidenceMembershipList(StudioDto):
    """One bounded cursor page of exact evaluation memberships."""

    items: tuple[EvidenceMembershipItem, ...] = Field(max_length=MAX_PAGE_SIZE)
    """Records in this response page; continue with next_cursor when present."""
    next_cursor: str | None
    """Opaque continuation token for the next page; None means there is no next page."""


class AttemptEvidenceBind(StudioDto):
    """Idempotent evidence-binding request for an attempt."""

    evidence: ExecutionEvidenceReference
    """Exact reference to the application target execution, not the evaluator execution."""


class AttemptResultWrite(StudioDto):
    """Idempotent terminal judgment request for an attempt."""

    status: Literal[
        AttemptStatus.PASSED,
        AttemptStatus.FAILED,
        AttemptStatus.ERROR,
    ]
    """Terminal result: passed or failed for a judgment, error for an execution or evaluator failure."""
    reason: ReasonText
    """Recorded explanation of the judgment or operational error."""
    duration_ms: int | None = Field(
        default=None,
        ge=0,
        le=MAX_DURATION_MS,
    )
    """Measured subject execution duration in milliseconds; None means unavailable, not zero."""


class ConflictResponse(StudioDto):
    """Machine-readable immutable-write conflict returned by Studio."""

    code: str
    """Machine-readable conflict code for programmatic handling."""
    message: str
    """Human-readable explanation of the conflict."""


class ExecutionResolutionRead(StudioDto):
    """Resolved owner span and semantic Studio paths for one execution."""

    service_namespace: str
    """OpenTelemetry service.namespace used to disambiguate execution identity."""
    service_name: str = Field(min_length=1)
    """OpenTelemetry service.name emitted by the application that owns the execution."""
    executable_type: ExecutableType
    """Native executable kind: workflow, subflow, or agent."""
    runtime_id: str = Field(min_length=1)
    """Per-invocation native execution identity; combine it with service identity and executable type."""
    trace_id: TraceId
    """OpenTelemetry trace identifier linking the complete recorded chronology."""
    span_id: SpanId
    """OpenTelemetry span identifier within the selected trace."""
    detail_path: str = Field(pattern=r"^/")
    """Relative Studio path to the resolved execution detail; join it to your Studio frontend origin."""
    trace_path: str = Field(pattern=r"^/")
    """Relative Studio path to the raw trace containing this execution."""
    failure_path: str = Field(pattern=r"^/")
    """Relative Studio path for investigating this execution failure."""


class OpenTelemetrySpanResolutionRead(StudioDto):
    """Direct trace paths for an already exact OpenTelemetry span reference."""

    service_namespace: ServiceNamespaceText
    """OpenTelemetry service.namespace used to disambiguate execution identity."""
    service_name: ExecutionIdentityText
    """OpenTelemetry service.name emitted by the application that owns the execution."""
    trace_id: TraceId
    """OpenTelemetry trace identifier linking the complete recorded chronology."""
    span_id: SpanId
    """OpenTelemetry span identifier within the selected trace."""
    detail_path: str = Field(pattern=r"^/")
    """Relative Studio path to the resolved execution detail; join it to your Studio frontend origin."""
    trace_path: str = Field(pattern=r"^/")
    """Relative Studio path to the raw trace containing this execution."""


class ExecutionResolutionConflict(StudioDto):
    """Ambiguous semantic identity returned by execution resolution."""

    code: Literal["ambiguous_execution_identity"]
    """Machine-readable conflict code for programmatic handling."""
    message: str = Field(min_length=1)
    """Human-readable explanation of the conflict."""
    match_count: int = Field(ge=2)
    """Number of executions matching an identity that was expected to be unique."""


class TraceEvidenceRead(StudioDto):
    """Complete normalized trace evidence hydrated only on explicit request.

    Studio owns the nested telemetry annotation domain.  This SDK contract
    deliberately validates the closed top-level envelope while preserving the
    nested JSON exactly for query and agent-driven analysis.
    """

    trace_id: str
    """OpenTelemetry trace identifier linking the complete recorded chronology."""
    spans: tuple[JsonObject, ...]
    """Complete recorded span JSON for this trace, including attributes and events allowed by capture policy."""
    executables_by_span_id: dict[str, JsonObject]
    """Native workflow, subflow, and agent annotations indexed by their owner span IDs."""
    operations_by_owner_runtime_id: dict[str, dict[str, JsonObject]]
    """Model and tool operation evidence grouped by owning runtime identity."""
    stores_by_id: dict[str, JsonObject]
    """Recorded state stores and transition evidence indexed by store identity."""
    relationships_by_owner_span_id: dict[str, JsonObject]
    """Parent and nested executable relationships indexed by owner span ID."""
    diagnostics: tuple[JsonObject, ...]
    """Evidence integrity diagnostics; use them to identify missing or inconsistent telemetry."""


class AttemptEvidence(StudioDto):
    """Attempt control context joined to its exact complete trace evidence."""

    attempt: AttemptDetail
    """Attempt together with its case, dataset, and run control context."""
    resolution: ExecutionResolutionRead | OpenTelemetrySpanResolutionRead
    """Resolved execution identity and relative Studio paths for the attempt subject."""
    evidence: TraceEvidenceRead
    """Complete normalized trace evidence; request a manifest first when only a compact investigation is needed."""


EvidenceSemanticKind = Literal[
    "agent",
    "workflow",
    "subflow",
    "node",
    "run_concurrent",
    "model",
    "tool",
    "span",
]
EvidenceOutcome = Literal["completed", "failed", "cancelled"]


class AttemptEvidenceSubject(StudioDto):
    """Exact Attempt subject and its resolved Studio evidence paths."""

    attempt_id: RecordId
    """Studio identifier of one case attempt within an evaluation run."""
    reference: ExecutionEvidenceReference
    """Exact native execution or OpenTelemetry span reference stored on the attempt."""
    trace_id: TraceId
    """OpenTelemetry trace identifier linking the complete recorded chronology."""
    span_id: SpanId
    """OpenTelemetry span identifier within the selected trace."""
    detail_path: str = Field(pattern=r"^/")
    """Relative Studio path to the resolved execution detail; join it to your Studio frontend origin."""
    failure_path: str = Field(pattern=r"^/")
    """Relative Studio path for investigating this execution failure."""
    trace_path: str = Field(pattern=r"^/")
    """Relative Studio path to the raw trace containing this execution."""


class AttemptEvidenceTraceSummary(StudioDto):
    """Bounded shape of the trace containing an evaluated subject."""

    trace_id: TraceId
    """OpenTelemetry trace identifier linking the complete recorded chronology."""
    span_count: int = Field(ge=1)
    """Number of spans recorded in the trace at the time it was read."""
    root_span_ids: tuple[SpanId, ...]
    """Spans without a parent present in the returned trace."""


class AttemptEvidenceSpanSummary(StudioDto):
    """Compact selectable identity and outcome for one span in a trace."""

    span_id: SpanId
    """OpenTelemetry span identifier within the selected trace."""
    parent_span_id: SpanId | None
    """Recorded parent span identifier; None for a span with no recorded parent."""
    name: str
    """Human-readable name retained with this record."""
    semantic_kind: EvidenceSemanticKind
    """Normalized meaning of the span, such as workflow, node, model, tool, or generic span."""
    status_code: str
    """Recorded OpenTelemetry status; application correctness is evaluated separately."""
    start_time: str
    """Recorded span start timestamp."""
    end_time: str
    """Recorded span end timestamp."""
    failed: bool
    """Whether recorded runtime evidence marks this span as failed; independent of the evaluation result."""
    span_path: str = Field(pattern=r"^/")
    """Relative Studio deep link selecting this span in the trace."""


class AttemptEvidenceFailureSummary(StudioDto):
    """Bounded failure facts for one failed span; complete detail is selectable."""

    span_id: SpanId
    """OpenTelemetry span identifier within the selected trace."""
    parent_span_id: SpanId | None
    """Recorded parent span identifier; None for a span with no recorded parent."""
    name: str
    """Human-readable name retained with this record."""
    semantic_kind: EvidenceSemanticKind
    """Normalized meaning of the span, such as workflow, node, model, tool, or generic span."""
    status_code: str
    """Recorded OpenTelemetry status; application correctness is evaluated separately."""
    start_time: str
    """Recorded span start timestamp."""
    end_time: str
    """Recorded span end timestamp."""
    exception_type: str | None
    """Recorded exception type, when the failed span supplied one."""
    exception_message: str | None
    """Recorded exception message, when available under the capture policy."""
    stacktrace_available: bool
    """Whether detailed evidence contains a stack trace that can be requested."""
    owner_span_id: SpanId | None
    """Span identity of the native executable that owns this evidence."""
    owner_runtime_id: str | None
    """Runtime identity of the native executable owner, when recorded."""
    span_path: str = Field(pattern=r"^/")
    """Relative Studio deep link selecting this span in the trace."""


class AttemptEvidenceExecutableSummary(StudioDto):
    """Compact semantic executable identity and integrity projection."""

    owner_span_id: SpanId
    """Span identity of the native executable that owns this evidence."""
    executable_type: Literal["agent", "workflow", "subflow"]
    """Native executable kind: workflow, subflow, or agent."""
    name: str
    """Human-readable name retained with this record."""
    runtime_id: str | None
    """Per-invocation native execution identity; combine it with service identity and executable type."""
    store_id: str | None
    """Identity of the application state store associated with the execution."""
    outcome: EvidenceOutcome | None
    """Recorded terminal lifecycle outcome; it does not replace an evaluator judgment."""
    status_code: str
    """Recorded OpenTelemetry status; application correctness is evaluated separately."""
    failed: bool
    """Whether recorded runtime evidence marks this executable as failed."""
    integrity: JsonObject
    """Studio-owned diagnostics describing the consistency of the recorded evidence."""


class AttemptEvidenceOperationSummary(StudioDto):
    """Compact model or Tool operation identity and terminal outcome."""

    owner_span_id: SpanId | None
    """Span identity of the native executable that owns this evidence."""
    owner_runtime_id: str | None
    """Runtime identity of the native executable owner, when recorded."""
    span_id: SpanId
    """OpenTelemetry span identifier within the selected trace."""
    operation_type: Literal["model_request", "tool"]
    """Whether this operation is a model request or a tool invocation."""
    name: str
    """Human-readable name retained with this record."""
    outcome: EvidenceOutcome
    """Recorded terminal lifecycle outcome; it does not replace an evaluator judgment."""
    duration_ns: int | None = Field(ge=0)
    """Recorded operation duration in nanoseconds; None means unavailable."""
    error_type: str | None
    """Recorded operation error type, when present."""
    error_message: str | None
    """Recorded operation error message, when present."""


class AttemptEvidenceStoreSummary(StudioDto):
    """Compact Store reconstruction status for one semantic executable owner."""

    store_id: str | None
    """Identity of the application state store associated with the execution."""
    owner_span_id: SpanId
    """Span identity of the native executable that owns this evidence."""
    owner_runtime_id: str | None
    """Runtime identity of the native executable owner, when recorded."""
    owner_executable_type: Literal["workflow", "subflow", "agent"]
    """Native executable kind that owns the store: workflow, subflow, or agent."""
    available: bool
    """Whether store evidence was available in the recorded telemetry."""
    transition_count: int = Field(ge=0)
    """Number of recorded state transitions for this store."""
    reconstructable: bool
    """Whether Studio verified that the recorded state transitions can be reconstructed."""
    reconstruction_status: Literal[
        "verified",
        "policy_unavailable",
        "failed",
        "not_applicable",
    ]
    """Whether reconstruction was verified, prevented by capture policy, failed, or was not applicable."""
    integrity: JsonObject
    """Studio-owned diagnostics describing the consistency of the recorded evidence."""


class AttemptEvidenceRelationships(StudioDto):
    """Parent and nested executable references attached to one owner span."""

    parent: JsonObject | None = None
    """Recorded parent executable relationship, or None when there is no relationship."""
    nested: tuple[JsonObject, ...] = ()
    """Recorded child executable relationships owned by this execution."""


class AttemptEvidenceDiagnostic(StudioDto):
    """One trace- or executable-scoped evidence integrity diagnostic."""

    scope: Literal["trace", "executable"]
    """Whether the integrity issue concerns the whole trace or one executable."""
    owner_span_id: SpanId | None = None
    """Span identity of the native executable that owns this evidence."""
    issue: JsonObject
    """Structured Studio evidence-integrity diagnostic, preserved as JSON."""


class AttemptEvidenceManifest(StudioDto):
    """Bounded trace manifest used to select evidence before full hydration."""

    subject: AttemptEvidenceSubject
    """Exact evaluated target identity and its Studio evidence paths."""
    trace: AttemptEvidenceTraceSummary
    """Compact trace identity and span-count information."""
    spans: tuple[AttemptEvidenceSpanSummary, ...]
    """Compact span identities and outcomes for selecting detailed evidence."""
    failures: tuple[AttemptEvidenceFailureSummary, ...]
    """Compact failed-span facts for choosing which full evidence to inspect."""
    executables: tuple[AttemptEvidenceExecutableSummary, ...]
    """Native executable summaries found in the attempt trace."""
    operations: tuple[AttemptEvidenceOperationSummary, ...]
    """Model and tool operation summaries associated with executable owners."""
    stores: tuple[AttemptEvidenceStoreSummary, ...]
    """State-store evidence associated with the selected execution or span."""
    relationships_by_owner_span_id: dict[str, AttemptEvidenceRelationships]
    """Parent and nested executable relationships indexed by owner span ID."""
    diagnostics: tuple[AttemptEvidenceDiagnostic, ...]
    """Evidence integrity diagnostics; use them to identify missing or inconsistent telemetry."""


class AttemptEvidenceSpanRequest(StudioDto):
    """Explicit non-empty set of span identities selected from one Attempt trace."""

    span_ids: tuple[SpanId, ...] = Field(min_length=1)
    """Unique span IDs selected from the attempt trace; request order is preserved."""

    @field_validator("span_ids")
    @classmethod
    def require_unique_span_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Reject ambiguous duplicate selections while preserving request order."""

        if len(value) != len(set(value)):
            raise ValueError("span_ids must not contain duplicates")
        return value


class AttemptEvidenceSpanItem(StudioDto):
    """Complete raw and directly associated semantic evidence for one span."""

    span: JsonObject
    """Complete recorded span JSON, including captured attributes and events."""
    executable: JsonObject | None
    """Native executable annotation directly associated with this span, when present."""
    operation: JsonObject | None
    """Model or tool operation annotation directly associated with this span, when present."""
    stores: tuple[JsonObject, ...]
    """State-store evidence associated with the selected execution or span."""
    relationships: AttemptEvidenceRelationships | None
    """Recorded parent and nested executable relationships associated with this span."""
    diagnostics: tuple[AttemptEvidenceDiagnostic, ...]
    """Evidence integrity diagnostics; use them to identify missing or inconsistent telemetry."""


class AttemptEvidenceSpans(StudioDto):
    """Selected span evidence in request order with explicit missing identities."""

    subject: AttemptEvidenceSubject
    """Exact evaluated target identity and its Studio evidence paths."""
    items: tuple[AttemptEvidenceSpanItem, ...]
    """Detailed evidence for the requested spans that were found, in request order."""
    missing_span_ids: tuple[SpanId, ...]
    """Requested span IDs absent from the recorded trace; do not infer their contents."""
