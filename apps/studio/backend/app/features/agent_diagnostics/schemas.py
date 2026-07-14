"""Public semantic API contracts for Agent execution diagnostics."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.features.store_diagnostics.schemas import (
    EvidenceDiagnostic,
    EvidenceIntegrity,
    PayloadEvidence,
    StoreDetail,
)
from app.features.telemetry_contract.types import (
    NonEmptyPortableText,
    PortableText,
    SafeNonNegativeInt,
    SafePositiveInt,
)


class ServiceIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    namespace: PortableText
    name: NonEmptyPortableText
    version: NonEmptyPortableText | None = None


class AgentExecutionListQuery(BaseModel):
    """Caller-owned filters; 422 is reserved for this transport boundary."""

    model_config = ConfigDict(extra="forbid")

    service_namespace: str = Field(description="Exact service.namespace; empty is explicit")
    service_name: str = Field(min_length=1, description="Exact service.name")
    agent_key: str | None = Field(default=None, min_length=1)
    structural_id: str | None = Field(default=None, min_length=1)
    service_version: str | None = Field(default=None, min_length=1)
    outcome: Literal["completed", "failed", "cancelled"] | None = None
    start_time: AwareDatetime | None = None
    end_time: AwareDatetime | None = None
    limit: int = Field(default=100, ge=1, le=250)

    @model_validator(mode="after")
    def validate_time_range(self) -> AgentExecutionListQuery:
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time > self.end_time
        ):
            raise ValueError("start_time must be earlier than or equal to end_time")
        return self


class AgentLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    model_requests: SafePositiveInt
    tool_calls: SafePositiveInt


class ToolCallCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    requested: SafeNonNegativeInt
    admitted: SafeNonNegativeInt
    started: SafeNonNegativeInt
    completed: SafeNonNegativeInt

    @model_validator(mode="after")
    def validate_monotonic_counts(self) -> ToolCallCounts:
        if not self.completed <= self.started <= self.admitted <= self.requested:
            raise ValueError(
                "Tool counts must satisfy completed <= started <= admitted <= requested"
            )
        return self


class AgentCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    operations: SafeNonNegativeInt
    model_requests: SafeNonNegativeInt
    tool_calls: ToolCallCounts


class UsageAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    sum: SafeNonNegativeInt
    observations: SafePositiveInt


class AgentUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    model_responses: SafeNonNegativeInt
    fields: dict[
        Literal[
            "inputTokens",
            "outputTokens",
            "cachedInputTokens",
            "reasoningTokens",
            "totalTokens",
        ],
        UsageAggregate,
    ]


class ModelUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    input_tokens: SafeNonNegativeInt | None = None
    output_tokens: SafeNonNegativeInt | None = None
    cached_input_tokens: SafeNonNegativeInt | None = None
    reasoning_tokens: SafeNonNegativeInt | None = None
    total_tokens: SafeNonNegativeInt | None = None


class AgentExecutionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    trace_id: str = Field(pattern="^[0-9a-f]{32}$")
    agent_span_id: str = Field(pattern="^[0-9a-f]{16}$")
    service: ServiceIdentity
    agent_key: NonEmptyPortableText
    agent_name: NonEmptyPortableText
    structural_id: str = Field(pattern="^agent_sha256:[0-9a-f]{64}$")
    definition_id: NonEmptyPortableText
    runtime_id: NonEmptyPortableText
    start_time: datetime
    end_time: datetime
    duration_ns: SafeNonNegativeInt
    outcome: Literal["completed", "failed", "cancelled"]
    termination_reason: Literal[
        "final_output",
        "input_validation_error",
        "history_validation_error",
        "limit_exceeded",
        "model_error",
        "model_response_error",
        "unknown_tool",
        "tool_input_validation_error",
        "tool_error",
        "tool_output_validation_error",
        "output_validation_error",
        "cancelled",
        "internal_error",
    ]
    limits: AgentLimits
    counts: AgentCounts
    usage: AgentUsage

    @model_validator(mode="after")
    def validate_summary_relationships(self) -> AgentExecutionSummary:
        expected_outcome = (
            "completed"
            if self.termination_reason == "final_output"
            else "cancelled"
            if self.termination_reason == "cancelled"
            else "failed"
        )
        if self.outcome != expected_outcome:
            raise ValueError("Agent outcome does not match its termination reason")
        if self.counts.operations < self.counts.model_requests:
            raise ValueError("operation count cannot be smaller than model request count")
        if self.counts.model_requests > self.limits.model_requests:
            raise ValueError("model request count exceeds its limit")
        if self.counts.tool_calls.admitted > self.limits.tool_calls:
            raise ValueError("admitted Tool count exceeds its limit")
        if self.usage.model_responses > self.counts.model_requests:
            raise ValueError("validated model responses cannot exceed model requests")
        return self


class CandidateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    available: bool
    payload: PayloadEvidence | None = None
    unavailable_reason: (
        Literal[
            "cancelled",
            "not_returned",
            "not_invoked",
            "service_failed",
            "not_json_serializable",
            "contract_evidence_missing",
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def validate_availability_shape(self) -> CandidateEvidence:
        if self.available:
            if self.payload is None or self.unavailable_reason is not None:
                raise ValueError("available candidate requires only payload evidence")
        elif self.payload is not None or not self.unavailable_reason:
            raise ValueError("unavailable candidate requires only an unavailable reason")
        return self


class ExecutionError(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: NonEmptyPortableText
    message: PortableText | None = None
    stacktrace: PortableText | None = None


class CancellationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    reason: NonEmptyPortableText


class RequestedToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    call_id: NonEmptyPortableText
    ordinal: SafePositiveInt
    tool_name: NonEmptyPortableText
    observed_tool_operation: bool
    admission: Literal["admitted", "not_admitted", "unknown"]
    reason: (
        Literal[
            "execution_interrupted",
            "store_evidence_unavailable",
            "tool_input_validation_error",
            "unknown_tool",
            "limit_exceeded",
            "batch_preflight_rejected",
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def validate_admission_shape(self) -> RequestedToolCall:
        if self.admission == "admitted":
            expected_reason = None if self.observed_tool_operation else "execution_interrupted"
            if self.reason != expected_reason:
                raise ValueError("admitted Tool-call execution evidence is inconsistent")
        elif self.admission == "not_admitted":
            if self.reason not in {
                "tool_input_validation_error",
                "unknown_tool",
                "limit_exceeded",
                "batch_preflight_rejected",
            }:
                raise ValueError("non-admitted Tool call requires a rejection reason")
        elif self.reason != "store_evidence_unavailable":
            raise ValueError("unknown admission requires unavailable Store evidence")
        return self


class ModelOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    operation_type: Literal["model_request"]
    sequence: SafePositiveInt
    span_id: str = Field(pattern="^[0-9a-f]{16}$")
    start_time: datetime
    end_time: datetime
    duration_ns: SafeNonNegativeInt
    ordinal: SafePositiveInt
    state_revision: SafeNonNegativeInt
    driver_key: NonEmptyPortableText
    provider: NonEmptyPortableText
    model_name: NonEmptyPortableText
    request: PayloadEvidence
    response_candidate: CandidateEvidence
    response_type: Literal["final_output", "tool_calls"] | None = None
    response: PayloadEvidence | None = None
    usage: ModelUsage | None = None
    requested_tool_calls: list[RequestedToolCall] = Field(default_factory=list)
    outcome: Literal["completed", "failed", "cancelled"]
    error: ExecutionError | None = None
    cancellation: CancellationEvidence | None = None

    @model_validator(mode="after")
    def validate_operation_shape(self) -> ModelOperation:
        _validate_operation_outcome(self.outcome, self.error, self.cancellation)
        if (self.response_type is None) != (self.response is None):
            raise ValueError("validated model response type and payload must be present together")
        if self.outcome == "completed" and self.response is None:
            raise ValueError("completed Model operation requires a validated response")
        if self.outcome != "completed" and (self.response is not None or self.usage is not None):
            raise ValueError("failed or cancelled Model operation cannot carry response evidence")
        if self.response_type != "tool_calls" and self.requested_tool_calls:
            raise ValueError("requested Tool calls require a validated Tool-calls response")
        if self.response_type is None and self.usage is not None:
            raise ValueError("usage requires a validated model response")
        return self


class ToolOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    operation_type: Literal["tool"]
    sequence: SafePositiveInt
    span_id: str = Field(pattern="^[0-9a-f]{16}$")
    start_time: datetime
    end_time: datetime
    duration_ns: SafeNonNegativeInt
    call_id: NonEmptyPortableText
    ordinal: SafePositiveInt
    tool_name: NonEmptyPortableText
    tool_structural_id: str = Field(pattern="^tool_sha256:[0-9a-f]{64}$")
    state_revision_before: SafeNonNegativeInt
    state_revision_after: SafeNonNegativeInt | None = None
    requested_arguments: PayloadEvidence
    arguments: PayloadEvidence | None = None
    result_candidate: CandidateEvidence
    result: PayloadEvidence | None = None
    outcome: Literal["completed", "failed", "cancelled"]
    error: ExecutionError | None = None
    cancellation: CancellationEvidence | None = None

    @model_validator(mode="after")
    def validate_operation_shape(self) -> ToolOperation:
        _validate_operation_outcome(self.outcome, self.error, self.cancellation)
        if self.outcome == "completed":
            if self.arguments is None or self.result is None or self.state_revision_after is None:
                raise ValueError(
                    "completed Tool operation requires validated arguments/result and revision"
                )
        elif self.result is not None or self.state_revision_after is not None:
            raise ValueError(
                "failed or cancelled Tool operation cannot carry committed result evidence"
            )
        if (self.result is None) != (self.state_revision_after is None):
            raise ValueError("Tool result and committed revision must be present together")
        return self


AgentOperation = Annotated[ModelOperation | ToolOperation, Field(discriminator="operation_type")]


class ParentExecutableReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    executable_type: Literal["workflow", "subflow", "node", "run_concurrent", "agent"]
    trace_id: str = Field(pattern="^[0-9a-f]{32}$")
    physical_parent_span_id: str = Field(pattern="^[0-9a-f]{16}$")
    span_id: str = Field(pattern="^[0-9a-f]{16}$")
    service: ServiceIdentity
    definition_id: NonEmptyPortableText
    runtime_id: NonEmptyPortableText
    structural_id: NonEmptyPortableText
    name: NonEmptyPortableText


class NestedExecutableReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    executable_type: Literal["workflow", "agent"]
    parent_operation_sequence: SafePositiveInt
    parent_operation_span_id: str = Field(pattern="^[0-9a-f]{16}$")
    trace_id: str = Field(pattern="^[0-9a-f]{32}$")
    span_id: str = Field(pattern="^[0-9a-f]{16}$")
    service: ServiceIdentity
    definition_id: NonEmptyPortableText
    runtime_id: NonEmptyPortableText
    structural_id: NonEmptyPortableText
    name: NonEmptyPortableText

    @model_validator(mode="after")
    def validate_structural_id(self) -> NestedExecutableReference:
        if self.executable_type == "agent" and not (
            self.structural_id.startswith("agent_sha256:")
            and len(self.structural_id) == 77
            and all(character in "0123456789abcdef" for character in self.structural_id[13:])
        ):
            raise ValueError("nested Agent structural ID is invalid")
        return self


class AgentExecutionDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    summary: AgentExecutionSummary
    definition: PayloadEvidence
    input: PayloadEvidence | None = None
    output: PayloadEvidence | None = None
    input_candidate: CandidateEvidence | None = None
    history_candidate: CandidateEvidence | None = None
    operations: list[AgentOperation]
    state: StoreDetail
    parent_executable: ParentExecutableReference | None = None
    nested_executables: list[NestedExecutableReference]
    error: ExecutionError | None = None
    cancellation: CancellationEvidence | None = None
    integrity: EvidenceIntegrity

    @model_validator(mode="after")
    def validate_terminal_evidence(self) -> AgentExecutionDetail:
        _validate_operation_outcome(self.summary.outcome, self.error, self.cancellation)
        if self.summary.outcome == "completed" and self.output is None:
            raise ValueError("completed Agent execution requires validated output evidence")
        if self.summary.outcome != "completed" and self.output is not None:
            raise ValueError(
                "non-completed Agent execution cannot contain validated output evidence"
            )
        return self


class AgentEvidenceErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: Literal["unsupported_contract", "unidentifiable_agent"]
    message: NonEmptyPortableText
    diagnostics: list[EvidenceDiagnostic] = Field(default_factory=list)


def _validate_operation_outcome(
    outcome: Literal["completed", "failed", "cancelled"],
    error: ExecutionError | None,
    cancellation: CancellationEvidence | None,
) -> None:
    if outcome == "completed" and (error is not None or cancellation is not None):
        raise ValueError("completed execution cannot contain error or cancellation evidence")
    if outcome == "failed" and cancellation is not None:
        raise ValueError("failed execution cannot contain cancellation evidence")
    if outcome == "cancelled" and (error is not None or cancellation is None):
        raise ValueError("cancelled execution requires only cancellation evidence")
