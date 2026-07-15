"""Shared strict decision envelope used by live provider adapters."""

import json
from typing import Any, Literal

from junjo.agent import (
    FinalOutputResponse,
    ModelRequest,
    ModelUsage,
    ToolCall,
    ToolCallsResponse,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProviderToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments_json: str = Field(min_length=2)


class ProviderDecision(BaseModel):
    """Provider-neutral structured output for one Junjo model operation."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["final_output", "tool_calls"]
    output_json: str | None = None
    tool_calls: list[ProviderToolCall] = Field(default_factory=list)
    assistant_text: str | None = None

    @model_validator(mode="after")
    def exact_variant(self) -> "ProviderDecision":
        if self.decision == "final_output":
            if self.output_json is None or self.tool_calls or self.assistant_text is not None:
                raise ValueError("A final decision requires only output.")
        elif self.output_json is not None or not self.tool_calls:
            raise ValueError("A Tool decision requires calls and no output.")
        return self

    def to_junjo(
        self,
        *,
        usage: ModelUsage | None = None,
    ) -> FinalOutputResponse | ToolCallsResponse:
        if self.decision == "final_output":
            assert self.output_json is not None
            return FinalOutputResponse(
                output=_json_object(self.output_json, "final output"),
                usage=usage,
            )
        return ToolCallsResponse(
            tool_calls=[
                ToolCall(
                    id=call.id,
                    name=call.name,
                    arguments=_json_object(call.arguments_json, "Tool arguments"),
                )
                for call in self.tool_calls
            ],
            assistant_text=self.assistant_text,
            usage=usage,
        )


def provider_prompt(request: ModelRequest) -> str:
    """Serialize the complete normalized Junjo intent without hidden state."""
    return (
        "Translate this Junjo Agent request into exactly one ProviderDecision. "
        "Use decision=tool_calls only when a declared tool is necessary. Put each "
        "Tool's arguments object in arguments_json as compact JSON text. Use "
        "decision=final_output when the typed final answer is ready and put that "
        "object in output_json as compact JSON text. Respect the declared output "
        "and Tool schemas. Do not invent Tool names or place application fields "
        "directly in the outer decision envelope.\n\n"
        + json.dumps(request.to_json(), separators=(",", ":"), ensure_ascii=False)
    )


def _json_object(value: str, label: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"Provider returned invalid {label} JSON.") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"Provider returned {label} JSON that is not an object.")
    return decoded
