"""Public contracts for lossless traces with verified semantic annotations."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.features.agent_diagnostics.schemas import (
    AgentExecutionSummary,
    AgentOperation,
    CancellationEvidence,
    CandidateEvidence,
    ExecutionError,
    NestedExecutableReference,
    ParentExecutableReference,
)
from app.features.evaluation.schemas import ExecutionEvidenceReference, RecordId
from app.features.store_diagnostics.schemas import (
    EvidenceDiagnostic,
    EvidenceIntegrity,
    PayloadEvidence,
    StoreDetail,
)

TraceId = Annotated[str, Field(pattern="^[0-9a-f]{32}$")]
SpanId = Annotated[str, Field(pattern="^[0-9a-f]{16}$")]


class NormalizedSpanEvidence(BaseModel):
    """One normalized span, including every field preserved by Studio storage."""

    model_config = ConfigDict(extra="forbid", strict=True)

    trace_id: str
    span_id: str
    parent_span_id: str | None
    service_name: str
    name: str
    kind: str
    start_time: str
    end_time: str
    status_code: str
    status_message: str
    attributes_json: dict[str, Any]
    events_json: list[Any]
    links_json: list[Any]
    trace_flags: int
    trace_state: str | None
    dropped_attributes_count: int
    dropped_events_count: int
    dropped_links_count: int
    resource_attributes_json: dict[str, Any]
    resource_dropped_attributes_count: int


class AgentExecutableAnnotation(BaseModel):
    """Verified Agent owner facts; operations and Store evidence remain indexed."""

    model_config = ConfigDict(extra="forbid", strict=True)

    executable_type: Literal["agent"]
    owner_span_id: str
    runtime_id: str
    store_id: str | None
    unavailable_store: StoreDetail | None = None
    summary: AgentExecutionSummary
    definition: PayloadEvidence
    input: PayloadEvidence | None = None
    output: PayloadEvidence | None = None
    input_candidate: CandidateEvidence | None = None
    history_candidate: CandidateEvidence | None = None
    error: ExecutionError | None = None
    cancellation: CancellationEvidence | None = None
    integrity: EvidenceIntegrity


class WorkflowExecutableAnnotation(BaseModel):
    """Verified Workflow owner facts; the Store is indexed independently."""

    model_config = ConfigDict(extra="forbid", strict=True)

    executable_type: Literal["workflow", "subflow"]
    owner_span_id: str
    name: str
    definition_id: str | None = None
    runtime_id: str | None = None
    structural_id: str | None = None
    store_id: str | None = None
    unavailable_store: StoreDetail | None = None
    integrity: EvidenceIntegrity


ExecutableAnnotation = Annotated[
    AgentExecutableAnnotation | WorkflowExecutableAnnotation,
    Field(discriminator="executable_type"),
]


class StoreAnnotation(BaseModel):
    """One independently verified executable Store, keyed by its Store ID."""

    model_config = ConfigDict(extra="forbid", strict=True)

    store_id: str
    owner_span_id: str
    owner_runtime_id: str | None = None
    owner_executable_type: Literal["workflow", "subflow", "agent"]
    detail: StoreDetail
    integrity: EvidenceIntegrity


class ExecutableRelationships(BaseModel):
    """Semantic executable boundaries discovered from one owner."""

    model_config = ConfigDict(extra="forbid", strict=True)

    parent: ParentExecutableReference | None = None
    nested: list[NestedExecutableReference] = Field(default_factory=list)


class TraceEvidenceDiagnostic(BaseModel):
    """A diagnostic scoped to the trace or to one executable owner."""

    model_config = ConfigDict(extra="forbid", strict=True)

    scope: Literal["trace", "executable"]
    owner_span_id: SpanId | None = None
    issue: EvidenceDiagnostic


class TraceEvidence(BaseModel):
    """Complete normalized telemetry plus generic verified annotations."""

    model_config = ConfigDict(extra="forbid", strict=True)

    trace_id: str
    spans: list[NormalizedSpanEvidence]
    executables_by_span_id: dict[str, ExecutableAnnotation]
    operations_by_owner_runtime_id: dict[str, dict[str, AgentOperation]]
    stores_by_id: dict[str, StoreAnnotation]
    relationships_by_owner_span_id: dict[str, ExecutableRelationships]
    diagnostics: list[TraceEvidenceDiagnostic]


SemanticSpanKind = Literal[
    "agent",
    "workflow",
    "subflow",
    "node",
    "run_concurrent",
    "model",
    "tool",
    "span",
]


class AttemptEvidenceSubject(BaseModel):
    """One bound evaluation subject resolved to exact stored evidence."""

    model_config = ConfigDict(extra="forbid", strict=True)

    attempt_id: RecordId
    reference: ExecutionEvidenceReference
    trace_id: TraceId
    span_id: SpanId
    detail_path: str = Field(pattern="^/")
    failure_path: str = Field(pattern="^/")
    trace_path: str = Field(pattern="^/")


class TraceManifestSummary(BaseModel):
    """Bounded identity and shape facts for one trace."""

    model_config = ConfigDict(extra="forbid", strict=True)

    trace_id: TraceId
    span_count: int = Field(ge=1)
    root_span_ids: list[SpanId]


class SpanManifestEntry(BaseModel):
    """Small selectable projection for one span."""

    model_config = ConfigDict(extra="forbid", strict=True)

    span_id: SpanId
    parent_span_id: SpanId | None
    name: str
    semantic_kind: SemanticSpanKind
    status_code: str
    start_time: str
    end_time: str
    failed: bool
    span_path: str = Field(pattern="^/")


class FailureSpanManifestEntry(BaseModel):
    """Failure signal without the span's large forensic payload fields."""

    model_config = ConfigDict(extra="forbid", strict=True)

    span_id: SpanId
    parent_span_id: SpanId | None
    name: str
    semantic_kind: SemanticSpanKind
    status_code: str
    start_time: str
    end_time: str
    exception_type: str | None
    exception_message: str | None
    stacktrace_available: bool
    owner_span_id: SpanId | None
    owner_runtime_id: str | None
    span_path: str = Field(pattern="^/")


class ExecutableManifestEntry(BaseModel):
    """Compact verified executable facts for triage."""

    model_config = ConfigDict(extra="forbid", strict=True)

    owner_span_id: SpanId
    executable_type: Literal["workflow", "subflow", "agent"]
    name: str
    runtime_id: str | None
    store_id: str | None
    outcome: Literal["completed", "failed", "cancelled"] | None
    status_code: str
    failed: bool
    integrity: EvidenceIntegrity


class OperationManifestEntry(BaseModel):
    """Compact verified Agent model or Tool operation facts."""

    model_config = ConfigDict(extra="forbid", strict=True)

    owner_span_id: SpanId | None
    owner_runtime_id: str | None
    span_id: SpanId
    operation_type: Literal["model_request", "tool"]
    name: str
    outcome: Literal["completed", "failed", "cancelled"]
    duration_ns: int | None = Field(ge=0)
    error_type: str | None
    error_message: str | None


class StoreManifestEntry(BaseModel):
    """Compact Store reconstruction and integrity facts."""

    model_config = ConfigDict(extra="forbid", strict=True)

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
    integrity: EvidenceIntegrity


class AttemptEvidenceManifest(BaseModel):
    """Trace-aware middle layer between an Attempt and complete evidence."""

    model_config = ConfigDict(extra="forbid", strict=True)

    subject: AttemptEvidenceSubject
    trace: TraceManifestSummary
    spans: list[SpanManifestEntry]
    failures: list[FailureSpanManifestEntry]
    executables: list[ExecutableManifestEntry]
    operations: list[OperationManifestEntry]
    stores: list[StoreManifestEntry]
    relationships_by_owner_span_id: dict[str, ExecutableRelationships]
    diagnostics: list[TraceEvidenceDiagnostic]


class SelectedSpanRequest(BaseModel):
    """Exact span identities selected from one Attempt's bound trace."""

    model_config = ConfigDict(extra="forbid", strict=True)

    span_ids: list[SpanId] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_span_ids(self) -> SelectedSpanRequest:
        if len(self.span_ids) != len(set(self.span_ids)):
            raise ValueError("span_ids must not contain duplicates")
        return self


class SelectedSpanEvidence(BaseModel):
    """One complete span plus semantic evidence directly owned by it."""

    model_config = ConfigDict(extra="forbid", strict=True)

    span: NormalizedSpanEvidence
    executable: ExecutableAnnotation | None
    operation: AgentOperation | None
    stores: list[StoreAnnotation]
    relationships: ExecutableRelationships | None
    diagnostics: list[TraceEvidenceDiagnostic]


class SelectedSpanEvidenceResponse(BaseModel):
    """Requested spans in caller order with explicit missing identities."""

    model_config = ConfigDict(extra="forbid", strict=True)

    subject: AttemptEvidenceSubject
    items: list[SelectedSpanEvidence]
    missing_span_ids: list[SpanId]
