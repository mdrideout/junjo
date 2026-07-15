"""Public semantic contracts for Workflow Store diagnostics."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.features.store_diagnostics.schemas import (
    EvidenceDiagnostic,
    EvidenceIntegrity,
    StoreDetail,
)
from app.features.telemetry_contract.types import NonEmptyPortableText


class WorkflowStoreDiagnostic(BaseModel):
    """Backend-authoritative Store projection for one Workflow executable."""

    model_config = ConfigDict(extra="forbid", strict=True)

    trace_id: str = Field(pattern="^[0-9a-f]{32}$")
    workflow_span_id: str = Field(pattern="^[0-9a-f]{16}$")
    executable_type: Literal["workflow", "subflow"]
    name: NonEmptyPortableText
    state: StoreDetail
    integrity: EvidenceIntegrity


class WorkflowEvidenceErrorResponse(BaseModel):
    """Typed rejection of unsupported or unidentifiable Workflow evidence."""

    model_config = ConfigDict(extra="forbid", strict=True)

    code: Literal["unsupported_contract", "unidentifiable_workflow"]
    message: NonEmptyPortableText
    diagnostics: list[EvidenceDiagnostic] = Field(default_factory=list)
