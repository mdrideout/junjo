"""Application-owned, portable evidence for deliberate live evaluations."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Literal
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from ai_chat.config import DebugSettings

ExecutableType = Literal["workflow", "agent"]
UsageFieldName = Literal[
    "inputTokens",
    "outputTokens",
    "cachedInputTokens",
    "reasoningTokens",
    "totalTokens",
]


class EvalUsageField(BaseModel):
    """One exact immutable token aggregate in an eval artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sum: int = Field(ge=0)
    observations: int = Field(ge=1)


class EvalUsage(BaseModel):
    """Portable versioned Agent usage evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    v: Literal[1] = 1
    modelResponses: int = Field(ge=0)
    fields: Mapping[UsageFieldName, EvalUsageField] = Field(default_factory=dict)

    @field_validator("fields")
    @classmethod
    def freeze_fields(
        cls,
        value: Mapping[UsageFieldName, EvalUsageField],
    ) -> Mapping[UsageFieldName, EvalUsageField]:
        return MappingProxyType(dict(value))

    @field_serializer("fields")
    def serialize_fields(
        self,
        value: Mapping[UsageFieldName, EvalUsageField],
    ) -> dict[str, dict[str, int]]:
        return {name: field.model_dump(mode="json") for name, field in value.items()}

    @model_validator(mode="after")
    def observations_do_not_exceed_responses(self) -> EvalUsage:
        if any(field.observations > self.modelResponses for field in self.fields.values()):
            raise ValueError("Usage observations cannot exceed modelResponses.")
        return self


class EvalResult(BaseModel):
    """One immutable evaluation outcome linked to its Junjo execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    object_type: Literal["ai_chat.eval_result"] = "ai_chat.eval_result"
    schema_version: Literal[1] = 1
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    executable_type: ExecutableType
    run_id: str = Field(min_length=1)
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    duration_ms: int = Field(ge=0)
    usage: EvalUsage | None = None
    studio_url: str | None = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvalResultRecorder:
    """Persist one JSON artifact per case without owning evaluation policy."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def record(self, result: EvalResult) -> Path:
        self._directory.mkdir(parents=True, exist_ok=True)
        filename = "--".join(_safe_filename(value) for value in (result.dataset_id, result.case_id, result.run_id))
        destination = self._directory / f"{filename}.json"
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
        return destination


def studio_execution_url(
    debug: DebugSettings,
    *,
    executable_type: ExecutableType,
    run_id: str,
) -> str | None:
    """Build the same authenticated runtime resolver URL used by the frontend."""

    if not debug.enabled or debug.studio_ui_url is None:
        return None
    query = urlencode(
        {
            "service_namespace": debug.service_namespace,
            "service_name": debug.service_name,
            "executable_type": executable_type,
            "runtime_id": run_id,
            "destination": "trace",
        }
    )
    return f"{debug.studio_ui_url}/resolve/executable?{query}"


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.")
    return normalized or "unnamed"
