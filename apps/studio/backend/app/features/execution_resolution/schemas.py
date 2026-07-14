"""Public contracts for exact executable identity resolution."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.features.telemetry_contract.types import NonEmptyPortableText, PortableText

ExecutableType = Literal["workflow", "subflow", "agent"]


class ExecutionResolutionQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_namespace: PortableText = Field(
        description="Exact service.namespace; empty is explicit"
    )
    service_name: NonEmptyPortableText = Field(description="Exact service.name")
    executable_type: ExecutableType
    runtime_id: NonEmptyPortableText


class ExecutionResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    service_namespace: PortableText
    service_name: NonEmptyPortableText
    executable_type: ExecutableType
    runtime_id: NonEmptyPortableText
    trace_id: str = Field(pattern="^[0-9a-f]{32}$")
    span_id: str = Field(pattern="^[0-9a-f]{16}$")
    detail_path: str = Field(pattern="^/")
    trace_path: str = Field(pattern="^/")


class ExecutionResolutionConflictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: Literal["ambiguous_execution_identity"]
    message: NonEmptyPortableText
    match_count: int = Field(ge=2)
