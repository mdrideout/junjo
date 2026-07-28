"""Public request and response contracts for Studio evaluations."""

from __future__ import annotations

import json
import math
from datetime import datetime
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

from app.db_sqlite.evaluation.models import (
    MAX_DESCRIPTION_BYTES,
    MAX_DURATION_MS,
    MAX_EXECUTION_IDENTITY_BYTES,
    MAX_JSON_BYTES,
    MAX_KEY_BYTES,
    MAX_NAME_BYTES,
    MAX_REASON_BYTES,
    MAX_VERSION,
)

MAX_CASES_PER_DATASET = 100
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
MAX_CURSOR_BYTES = 1_024

DatasetStatus = Literal["draft", "locked"]
CaseOrigin = Literal["authored", "generated"]
TargetKind = Literal["node", "workflow", "agent"]
ExecutableType = Literal["workflow", "subflow", "agent"]
RunStatus = Literal["active", "completed"]
AttemptStatus = Literal["queued", "passed", "failed", "error"]
TerminalAttemptStatus = Literal["passed", "failed", "error"]
ExecutionMembershipRole = Literal["case_source", "attempt_subject"]


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
RecordId = Annotated[str, Field(min_length=1, max_length=64)]


def dump_bounded_json(value: JsonValue) -> str:
    """Serialize application JSON deterministically for limits and idempotency."""
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


def load_stored_json(value: str) -> JsonValue:
    """Parse JSON previously validated at the write boundary."""
    return json.loads(value)


class EvaluationContract(BaseModel):
    """Closed base contract used by every evaluation request and response."""

    model_config = ConfigDict(extra="forbid")


class SemanticExecutionReference(EvaluationContract):
    service_namespace: ServiceNamespaceText = Field(
        description="Exact normalized service.namespace; empty is explicit",
        examples=["junjo.examples"],
    )
    service_name: ExecutionIdentityText = Field(examples=["ai-chat-evaluation"])
    executable_type: ExecutableType
    runtime_id: ExecutionIdentityText = Field(examples=["workflowRun123"])


class EvaluationDatasetCreate(EvaluationContract):
    application_key: KeyText = Field(examples=["ai_chat"])
    key: KeyText = Field(examples=["local_place_realism_v1"])
    name: NameText = Field(examples=["Local place realism"])
    description: DescriptionText | None = Field(default=None)


class EvaluationDatasetSummary(EvaluationContract):
    id: RecordId
    application_key: KeyText
    key: KeyText
    name: NameText
    status: DatasetStatus


class EvaluationDatasetRead(EvaluationDatasetSummary):
    description: DescriptionText | None
    created_by_user_id: RecordId | None
    created_at: datetime
    locked_at: datetime | None


class EvaluationCaseCreate(EvaluationContract):
    case_key: KeyText = Field(examples=["specific_place_1"])
    origin: CaseOrigin
    target_kind: TargetKind
    target_key: KeyText = Field(examples=["date_response_node"])
    input_version: int = Field(ge=1, le=MAX_VERSION)
    input_json: JsonValue
    expectation_json: JsonValue | None = None
    evaluator_key: KeyText = Field(examples=["response_quality"])
    evaluator_version: int = Field(ge=1, le=MAX_VERSION)
    source_execution: SemanticExecutionReference | None = None
    source_revision: SourceRevision | None = None

    @field_validator("input_json")
    @classmethod
    def validate_input_json_size(cls, value: JsonValue) -> JsonValue:
        dump_bounded_json(value)
        return value

    @field_validator("expectation_json")
    @classmethod
    def validate_expectation_json_size(cls, value: JsonValue | None) -> JsonValue | None:
        if value is not None:
            dump_bounded_json(value)
        return value

    @model_validator(mode="after")
    def validate_source_provenance(self) -> EvaluationCaseCreate:
        if self.origin == "authored":
            if self.source_execution is not None or self.source_revision is not None:
                raise ValueError("authored cases cannot include source provenance")
            return self
        if self.source_execution is None or self.source_revision is None:
            raise ValueError("generated cases require both source_execution and source_revision")
        return self


class EvaluationCaseRead(EvaluationContract):
    id: RecordId
    dataset_id: RecordId
    case_key: KeyText
    ordinal: int = Field(ge=1)
    origin: CaseOrigin
    target_kind: TargetKind
    target_key: KeyText
    input_version: int = Field(ge=1, le=MAX_VERSION)
    input_json: JsonValue
    expectation_json: JsonValue | None
    evaluator_key: KeyText
    evaluator_version: int = Field(ge=1, le=MAX_VERSION)
    source_execution: SemanticExecutionReference | None
    source_revision: SourceRevision | None
    created_at: datetime


class EvaluationDatasetDetail(EvaluationContract):
    dataset: EvaluationDatasetRead
    cases: list[EvaluationCaseRead] = Field(max_length=MAX_CASES_PER_DATASET)


class EvaluationDatasetList(EvaluationContract):
    items: list[EvaluationDatasetRead] = Field(max_length=MAX_PAGE_SIZE)
    next_cursor: str | None


class EvaluationRunStart(EvaluationContract):
    dataset_id: RecordId
    request_key: KeyText = Field(examples=["baseline-20260727"])
    candidate_label: NameText = Field(examples=["baseline"])
    source_revision: SourceRevision


class EvaluationRunRead(EvaluationContract):
    id: RecordId
    dataset_id: RecordId
    request_key: KeyText
    candidate_label: NameText
    source_revision: SourceRevision
    status: RunStatus
    created_by_user_id: RecordId | None
    created_at: datetime
    completed_at: datetime | None


class EvaluationAttemptRead(EvaluationContract):
    id: RecordId
    run_id: RecordId
    case_id: RecordId
    status: AttemptStatus
    score: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    reason: ReasonText | None
    duration_ms: int | None = Field(default=None, ge=0, le=MAX_DURATION_MS)
    subject_execution: SemanticExecutionReference | None
    execution_bound_at: datetime | None
    recorded_at: datetime | None


class EvaluationRunCase(EvaluationContract):
    case: EvaluationCaseRead
    attempt: EvaluationAttemptRead


class EvaluationRunDetail(EvaluationContract):
    run: EvaluationRunRead
    dataset: EvaluationDatasetRead
    cases: list[EvaluationRunCase] = Field(max_length=MAX_CASES_PER_DATASET)


class EvaluationAttemptDetail(EvaluationContract):
    run: EvaluationRunRead
    dataset: EvaluationDatasetRead
    case: EvaluationCaseRead
    attempt: EvaluationAttemptRead


class EvaluationAttemptCounts(EvaluationContract):
    total: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    queued: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    passed: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    failed: int = Field(ge=0, le=MAX_CASES_PER_DATASET)
    error: int = Field(ge=0, le=MAX_CASES_PER_DATASET)


class EvaluationRunSummary(EvaluationContract):
    run: EvaluationRunRead
    dataset: EvaluationDatasetSummary
    attempt_counts: EvaluationAttemptCounts


class EvaluationRunList(EvaluationContract):
    items: list[EvaluationRunSummary] = Field(max_length=MAX_PAGE_SIZE)
    next_cursor: str | None


class EvaluationExecutionBind(EvaluationContract):
    execution: SemanticExecutionReference


class EvaluationAttemptResult(EvaluationContract):
    status: TerminalAttemptStatus
    score: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    reason: ReasonText
    duration_ms: int | None = Field(default=None, ge=0, le=MAX_DURATION_MS)

    @model_validator(mode="after")
    def validate_terminal_result(self) -> EvaluationAttemptResult:
        if self.status in ("passed", "failed"):
            if self.score is None:
                raise ValueError("passed and failed results require score")
        elif self.score is not None:
            raise ValueError("error results cannot include score")
        if self.score is not None and not math.isfinite(self.score):
            raise ValueError("score must be finite")
        return self


class EvaluationExecutionMembership(EvaluationContract):
    role: ExecutionMembershipRole
    dataset_id: RecordId
    case_id: RecordId
    run_id: RecordId | None
    attempt_id: RecordId | None

    @model_validator(mode="after")
    def validate_role_identity(self) -> EvaluationExecutionMembership:
        if self.role == "case_source":
            if self.run_id is not None or self.attempt_id is not None:
                raise ValueError("case_source membership cannot include run or attempt IDs")
        elif self.run_id is None or self.attempt_id is None:
            raise ValueError("attempt_subject membership requires run and attempt IDs")
        return self


class EvaluationExecutionMembershipList(EvaluationContract):
    items: list[EvaluationExecutionMembership] = Field(max_length=MAX_PAGE_SIZE)
    next_cursor: str | None


class EvaluationConflictResponse(EvaluationContract):
    code: str
    message: str
