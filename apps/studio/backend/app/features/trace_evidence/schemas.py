"""Public contracts for lossless traces with verified semantic annotations."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.features.agent_diagnostics.schemas import (
    AgentExecutionSummary,
    AgentOperation,
    CancellationEvidence,
    CandidateEvidence,
    ExecutionError,
    NestedExecutableReference,
    ParentExecutableReference,
)
from app.features.store_diagnostics.schemas import (
    EvidenceDiagnostic,
    EvidenceIntegrity,
    PayloadEvidence,
    StoreDetail,
)


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
    owner_span_id: str | None = None
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
