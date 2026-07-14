"""Shared strict decision envelope used by live provider adapters."""

import json
from typing import Any, Literal

from junjo.agent import FinalOutputResponse, ModelRequest, ToolCall, ToolCallsResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProviderToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: dict[str, Any]


class ProviderDecision(BaseModel):
    """Provider-neutral structured output for one Junjo model operation."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["final_output", "tool_calls"]
    output: dict[str, Any] | None = None
    tool_calls: list[ProviderToolCall] = Field(default_factory=list)
    assistant_text: str | None = None

    @model_validator(mode="after")
    def exact_variant(self) -> "ProviderDecision":
        if self.decision == "final_output":
            if self.output is None or self.tool_calls:
                raise ValueError("A final decision requires only output.")
        elif self.output is not None or not self.tool_calls:
            raise ValueError("A Tool decision requires calls and no output.")
        return self

    def to_junjo(self) -> FinalOutputResponse | ToolCallsResponse:
        if self.decision == "final_output":
            assert self.output is not None
            return FinalOutputResponse(output=self.output)
        return ToolCallsResponse(
            tool_calls=[ToolCall(id=call.id, name=call.name, arguments=call.arguments) for call in self.tool_calls],
            assistant_text=self.assistant_text,
        )


def provider_prompt(request: ModelRequest) -> str:
    """Serialize the complete normalized Junjo intent without hidden state."""
    return (
        "Translate this Junjo Agent request into exactly one ProviderDecision. "
        "Use decision=tool_calls only when a declared tool is necessary. Use "
        "decision=final_output when the typed final answer is ready. Respect the "
        "declared output and tool schemas. Do not invent tool names.\n\n"
        + json.dumps(request.to_json(), separators=(",", ":"), ensure_ascii=False)
    )
