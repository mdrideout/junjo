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
    version: str = Field(min_length=1)
    app_name: str = Field(min_length=1)


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
    service_namespace: ServiceNamespaceText = Field(
        description="Exact normalized service.namespace; empty is explicit",
    )
    service_name: ExecutionIdentityText
    executable_type: ExecutableType
    runtime_id: ExecutionIdentityText


class OpenTelemetrySpanReference(StudioDto):
    """Exact OpenTelemetry span identity used for external execution evidence."""

    kind: Literal["otel_span"] = "otel_span"
    service_namespace: ServiceNamespaceText = Field(
        description="Exact normalized service.namespace; empty is explicit",
    )
    service_name: ExecutionIdentityText
    trace_id: TraceId
    span_id: SpanId


ExecutionEvidenceReference = Annotated[
    SemanticExecutionReference | OpenTelemetrySpanReference,
    Field(discriminator="kind"),
]


class DatasetCreate(StudioDto):
    """Request to create an idempotently keyed evaluation dataset."""

    application_key: KeyText
    key: KeyText
    name: NameText
    description: DescriptionText | None = None


class DatasetSummary(StudioDto):
    """Bounded dataset projection embedded in run-list responses."""

    id: RecordId
    application_key: KeyText
    key: KeyText
    name: NameText
    status: DatasetStatus


class DatasetRead(DatasetSummary):
    """Complete evaluation dataset control record."""

    description: DescriptionText | None
    created_by_user_id: RecordId | None
    created_at: datetime
    locked_at: datetime | None


class CaseCreate(StudioDto):
    """Request to append one immutable input case to a draft dataset."""

    case_key: KeyText
    evaluation_name: NameText
    origin: CaseOrigin
    target_kind: TargetKind
    target_key: KeyText
    target_name: NameText
    input_version: int = Field(ge=1, le=MAX_VERSION)
    input_json: JsonValue
    expectation_json: JsonValue | None = None
    evaluator_key: KeyText
    evaluator_version: int = Field(ge=1, le=MAX_VERSION)
    source_evidence: ExecutionEvidenceReference | None = None
    source_revision: SourceRevision | None = None

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
    dataset_id: RecordId
    case_key: KeyText
    evaluation_name: NameText
    ordinal: int = Field(ge=1)
    origin: CaseOrigin
    target_kind: TargetKind
    target_key: KeyText
    target_name: NameText
    input_version: int = Field(ge=1, le=MAX_VERSION)
    input_json: JsonValue
    expectation_json: JsonValue | None
    evaluator_key: KeyText
    evaluator_version: int = Field(ge=1, le=MAX_VERSION)
    source_evidence: ExecutionEvidenceReference | None
    source_revision: SourceRevision | None
    created_at: datetime


class DatasetDetail(StudioDto):
    """A dataset and its bounded, ordinal case membership."""

    dataset: DatasetRead
    cases: tuple[CaseRead, ...] = Field(max_length=MAX_CASES_PER_DATASET)


class DatasetList(StudioDto):
    """One bounded cursor page of evaluation datasets."""

    items: tuple[DatasetRead, ...] = Field(max_length=MAX_PAGE_SIZE)
    next_cursor: str | None


class RunStart(StudioDto):
    """Request to create or retrieve one idempotently keyed labeled run."""

    dataset_id: RecordId
    request_key: KeyText
    run_label: NameText
    source_revision: SourceRevision


class RunRead(StudioDto):
    """Evaluation run control record."""

    id: RecordId
    dataset_id: RecordId
    request_key: KeyText
    run_label: NameText
    source_revision: SourceRevision
    status: RunStatus
    created_by_user_id: RecordId | None
    created_at: datetime
    completed_at: datetime | None


class AttemptRead(StudioDto):
    """One case attempt, including terminal judgment and execution binding."""

    id: RecordId
    run_id: RecordId
    case_id: RecordId
    status: AttemptStatus
    reason: ReasonText | None
    duration_ms: int | None = Field(
        default=None,
        ge=0,
        le=MAX_DURATION_MS,
    )
    subject_evidence: ExecutionEvidenceReference | None
    evidence_bound_at: datetime | None
    recorded_at: datetime | None


class RunCaseRead(StudioDto):
    """A locked case paired with its attempt in one run."""

    case: CaseRead
    attempt: AttemptRead


class RunDetail(StudioDto):
    """A run, locked dataset, and complete bounded case-attempt membership."""

    run: RunRead
    dataset: DatasetRead
    cases: tuple[RunCaseRead, ...] = Field(max_length=MAX_CASES_PER_DATASET)


class AttemptDetail(StudioDto):
    """Self-contained control context for one attempt."""

    run: RunRead
    dataset: DatasetRead
    case: CaseRead
    attempt: AttemptRead


class RunScope(StudioDto):
    """The exact, conjunctive case scope applied to a run-list projection."""

    dataset_id: RecordId | None = None
    target_kind: TargetKind | None = None
    target_key: KeyText | None = None
    input_version: int | None = Field(default=None, ge=1, le=MAX_VERSION)
    evaluation_name: NameText | None = None


class OutcomeSummary(StudioDto):
    """Bounded outcome aggregates for the attempts visible in one scope."""

    total: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    queued: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    judged: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    passed: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    failed: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    error: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    pass_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    coverage: float | None = Field(default=None, ge=0.0, le=1.0)


class TargetFacet(StudioDto):
    """One target identity and its case count in a run's dataset."""

    target_kind: TargetKind
    target_key: KeyText
    target_name: NameText
    input_version: int = Field(ge=1, le=MAX_VERSION)
    case_count: int = Field(ge=1, le=MAX_CASES_PER_DATASET)


class EvaluationNameFacet(StudioDto):
    """One human evaluation name and its case count in a run's dataset."""

    evaluation_name: NameText
    case_count: int = Field(ge=1, le=MAX_CASES_PER_DATASET)


class RunSummary(StudioDto):
    """Bounded run-list projection."""

    run: RunRead
    dataset: DatasetSummary
    outcome_summary: OutcomeSummary
    target_facets: tuple[TargetFacet, ...] = Field(max_length=MAX_CASES_PER_DATASET)
    evaluation_facets: tuple[EvaluationNameFacet, ...] = Field(max_length=MAX_CASES_PER_DATASET)


class RunList(StudioDto):
    """One bounded cursor page of evaluation runs."""

    scope: RunScope
    items: tuple[RunSummary, ...] = Field(max_length=MAX_PAGE_SIZE)
    next_cursor: str | None


class EvidenceMembershipItem(StudioDto):
    """One exact case-source or attempt-subject membership."""

    role: Literal["case_source", "attempt_subject"]
    dataset_id: RecordId
    case_id: RecordId
    run_id: RecordId | None
    attempt_id: RecordId | None

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
    next_cursor: str | None


class AttemptEvidenceBind(StudioDto):
    """Idempotent evidence-binding request for an attempt."""

    evidence: ExecutionEvidenceReference


class AttemptResultWrite(StudioDto):
    """Idempotent terminal judgment request for an attempt."""

    status: Literal[
        AttemptStatus.PASSED,
        AttemptStatus.FAILED,
        AttemptStatus.ERROR,
    ]
    reason: ReasonText
    duration_ms: int | None = Field(
        default=None,
        ge=0,
        le=MAX_DURATION_MS,
    )


class ConflictResponse(StudioDto):
    """Machine-readable immutable-write conflict returned by Studio."""

    code: str
    message: str


class ExecutionResolutionRead(StudioDto):
    """Resolved owner span and semantic Studio paths for one execution."""

    service_namespace: str
    service_name: str = Field(min_length=1)
    executable_type: ExecutableType
    runtime_id: str = Field(min_length=1)
    trace_id: TraceId
    span_id: SpanId
    detail_path: str = Field(pattern=r"^/")
    trace_path: str = Field(pattern=r"^/")
    failure_path: str = Field(pattern=r"^/")


class OpenTelemetrySpanResolutionRead(StudioDto):
    """Direct trace paths for an already exact OpenTelemetry span reference."""

    service_namespace: ServiceNamespaceText
    service_name: ExecutionIdentityText
    trace_id: TraceId
    span_id: SpanId
    detail_path: str = Field(pattern=r"^/")
    trace_path: str = Field(pattern=r"^/")


class ExecutionResolutionConflict(StudioDto):
    """Ambiguous semantic identity returned by execution resolution."""

    code: Literal["ambiguous_execution_identity"]
    message: str = Field(min_length=1)
    match_count: int = Field(ge=2)


class TraceEvidenceRead(StudioDto):
    """Complete normalized trace evidence hydrated only on explicit request.

    Studio owns the nested telemetry annotation domain.  This SDK contract
    deliberately validates the closed top-level envelope while preserving the
    nested JSON exactly for query and agent-driven analysis.
    """

    trace_id: str
    spans: tuple[JsonObject, ...]
    executables_by_span_id: dict[str, JsonObject]
    operations_by_owner_runtime_id: dict[str, dict[str, JsonObject]]
    stores_by_id: dict[str, JsonObject]
    relationships_by_owner_span_id: dict[str, JsonObject]
    diagnostics: tuple[JsonObject, ...]


class AttemptEvidence(StudioDto):
    """Attempt control context joined to its exact complete trace evidence."""

    attempt: AttemptDetail
    resolution: ExecutionResolutionRead | OpenTelemetrySpanResolutionRead
    evidence: TraceEvidenceRead


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
    reference: ExecutionEvidenceReference
    trace_id: TraceId
    span_id: SpanId
    detail_path: str = Field(pattern=r"^/")
    failure_path: str = Field(pattern=r"^/")
    trace_path: str = Field(pattern=r"^/")


class AttemptEvidenceTraceSummary(StudioDto):
    """Bounded shape of the trace containing an evaluated subject."""

    trace_id: TraceId
    span_count: int = Field(ge=1)
    root_span_ids: tuple[SpanId, ...]


class AttemptEvidenceSpanSummary(StudioDto):
    """Compact selectable identity and outcome for one span in a trace."""

    span_id: SpanId
    parent_span_id: SpanId | None
    name: str
    semantic_kind: EvidenceSemanticKind
    status_code: str
    start_time: str
    end_time: str
    failed: bool
    span_path: str = Field(pattern=r"^/")


class AttemptEvidenceFailureSummary(StudioDto):
    """Bounded failure facts for one failed span; complete detail is selectable."""

    span_id: SpanId
    parent_span_id: SpanId | None
    name: str
    semantic_kind: EvidenceSemanticKind
    status_code: str
    start_time: str
    end_time: str
    exception_type: str | None
    exception_message: str | None
    stacktrace_available: bool
    owner_span_id: SpanId | None
    owner_runtime_id: str | None
    span_path: str = Field(pattern=r"^/")


class AttemptEvidenceExecutableSummary(StudioDto):
    """Compact semantic executable identity and integrity projection."""

    owner_span_id: SpanId
    executable_type: Literal["agent", "workflow", "subflow"]
    name: str
    runtime_id: str | None
    store_id: str | None
    outcome: EvidenceOutcome | None
    status_code: str
    failed: bool
    integrity: JsonObject


class AttemptEvidenceOperationSummary(StudioDto):
    """Compact model or Tool operation identity and terminal outcome."""

    owner_span_id: SpanId | None
    owner_runtime_id: str | None
    span_id: SpanId
    operation_type: Literal["model_request", "tool"]
    name: str
    outcome: EvidenceOutcome
    duration_ns: int | None = Field(ge=0)
    error_type: str | None
    error_message: str | None


class AttemptEvidenceStoreSummary(StudioDto):
    """Compact Store reconstruction status for one semantic executable owner."""

    store_id: str | None
    owner_span_id: SpanId
    owner_runtime_id: str | None
    owner_executable_type: Literal["workflow", "subflow", "agent"]
    available: bool
    transition_count: int = Field(ge=0)
    reconstructable: bool
    reconstruction_status: Literal[
        "verified",
        "policy_unavailable",
        "failed",
        "not_applicable",
    ]
    integrity: JsonObject


class AttemptEvidenceRelationships(StudioDto):
    """Parent and nested executable references attached to one owner span."""

    parent: JsonObject | None = None
    nested: tuple[JsonObject, ...] = ()


class AttemptEvidenceDiagnostic(StudioDto):
    """One trace- or executable-scoped evidence integrity diagnostic."""

    scope: Literal["trace", "executable"]
    owner_span_id: SpanId | None = None
    issue: JsonObject


class AttemptEvidenceManifest(StudioDto):
    """Bounded trace manifest used to select evidence before full hydration."""

    subject: AttemptEvidenceSubject
    trace: AttemptEvidenceTraceSummary
    spans: tuple[AttemptEvidenceSpanSummary, ...]
    failures: tuple[AttemptEvidenceFailureSummary, ...]
    executables: tuple[AttemptEvidenceExecutableSummary, ...]
    operations: tuple[AttemptEvidenceOperationSummary, ...]
    stores: tuple[AttemptEvidenceStoreSummary, ...]
    relationships_by_owner_span_id: dict[str, AttemptEvidenceRelationships]
    diagnostics: tuple[AttemptEvidenceDiagnostic, ...]


class AttemptEvidenceSpanRequest(StudioDto):
    """Explicit non-empty set of span identities selected from one Attempt trace."""

    span_ids: tuple[SpanId, ...] = Field(min_length=1)

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
    executable: JsonObject | None
    operation: JsonObject | None
    stores: tuple[JsonObject, ...]
    relationships: AttemptEvidenceRelationships | None
    diagnostics: tuple[AttemptEvidenceDiagnostic, ...]


class AttemptEvidenceSpans(StudioDto):
    """Selected span evidence in request order with explicit missing identities."""

    subject: AttemptEvidenceSubject
    items: tuple[AttemptEvidenceSpanItem, ...]
    missing_span_ids: tuple[SpanId, ...]
