"""Detached Agent execution result and usage summaries."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Generic, TypeVar

from .._json import require_ijson_integer, require_ijson_text
from .messages import (
    AgentInputMessage,
    AgentMessage,
    AssistantOutputMessage,
    AssistantToolCallsMessage,
    ModelUsage,
    ToolResultMessage,
    validate_history,
)

OutputT = TypeVar("OutputT")

USAGE_FIELDS = (
    "inputTokens",
    "outputTokens",
    "cachedInputTokens",
    "reasoningTokens",
    "totalTokens",
)

_AGENT_STRUCTURAL_ID = re.compile(r"agent_sha256:[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class UsageAggregateField:
    """Sum and observation count for one optional provider usage fact."""

    sum: int
    observations: int

    def __post_init__(self) -> None:
        require_ijson_integer(self.sum, "Usage aggregate sum", minimum=0)
        require_ijson_integer(
            self.observations, "Usage aggregate observations", minimum=1
        )


@dataclass(frozen=True, slots=True, init=False)
class AgentUsage:
    """Aggregate of validated per-response provider usage facts."""

    model_responses: int
    fields: Mapping[str, UsageAggregateField]

    def __init__(
        self,
        *,
        model_responses: int = 0,
        fields: Mapping[str, UsageAggregateField] | None = None,
    ) -> None:
        """Create a validated immutable aggregate.

        :param model_responses: Count of validated model responses, including
            responses whose provider reported no usage.
        :param fields: Supported token fact aggregates only.
        """
        require_ijson_integer(model_responses, "model_responses", minimum=0)
        supplied_fields = dict(fields or {})
        unsupported = set(supplied_fields) - set(USAGE_FIELDS)
        if unsupported:
            raise ValueError(f"Unsupported usage aggregate fields: {sorted(unsupported)}")
        if any(not isinstance(value, UsageAggregateField) for value in supplied_fields.values()):
            raise TypeError("AgentUsage fields must contain UsageAggregateField values.")
        if any(
            value.observations > model_responses for value in supplied_fields.values()
        ):
            raise ValueError(
                "Usage field observations cannot exceed model_responses."
            )
        object.__setattr__(self, "model_responses", model_responses)
        object.__setattr__(self, "fields", MappingProxyType(supplied_fields))

    def add(self, usage: ModelUsage | None) -> AgentUsage:
        fields = dict(self.fields)
        if usage is not None:
            names = {
                "input_tokens": "inputTokens",
                "output_tokens": "outputTokens",
                "cached_input_tokens": "cachedInputTokens",
                "reasoning_tokens": "reasoningTokens",
                "total_tokens": "totalTokens",
            }
            for attr, name in names.items():
                value = getattr(usage, attr)
                if value is None:
                    continue
                previous = fields.get(name)
                previous_sum = previous.sum if previous is not None else 0
                previous_observations = previous.observations if previous is not None else 0
                fields[name] = UsageAggregateField(
                    sum=previous_sum + value,
                    observations=previous_observations + 1,
                )
        return AgentUsage(model_responses=self.model_responses + 1, fields=fields)

    def to_json(self) -> dict[str, object]:
        return {
            "v": 1,
            "modelResponses": self.model_responses,
            "fields": {
                name: {"sum": field.sum, "observations": field.observations}
                for name, field in self.fields.items()
            },
        }


@dataclass(frozen=True, slots=True, init=False)
class AgentExecutionResult(Generic[OutputT]):
    """Frozen detached result returned only after validated final output."""

    agent_key: str
    name: str
    definition_id: str
    structural_id: str
    run_id: str
    output: OutputT
    transcript: tuple[AgentMessage, ...]
    usage: AgentUsage
    model_request_count: int
    tool_call_requested_count: int
    tool_call_admitted_count: int
    tool_call_started_count: int
    tool_call_completed_count: int
    termination_reason: str

    def __init__(
        self,
        *,
        agent_key: str,
        name: str,
        definition_id: str,
        structural_id: str,
        run_id: str,
        output: OutputT,
        transcript: tuple[AgentMessage, ...],
        usage: AgentUsage,
        model_request_count: int,
        tool_call_requested_count: int,
        tool_call_admitted_count: int,
        tool_call_started_count: int,
        tool_call_completed_count: int,
    ) -> None:
        """Create a detached successful Agent execution result.

        The public constructor enforces portable identities, exact Agent
        fingerprint form, a complete normalized transcript, usage/request
        consistency, and ``completed <= started <= admitted <= requested``.

        :param output: Already validated typed output owned by the caller.
        :param transcript: One or more complete normalized exchanges.
        :param usage: Immutable aggregate usage evidence.
        :raises TypeError: If typed members have the wrong public type.
        :raises ValueError: If identities, transcript, or counters conflict.
        """
        identities = _validated_result_identities(
            agent_key=agent_key,
            name=name,
            definition_id=definition_id,
            structural_id=structural_id,
            run_id=run_id,
        )
        counts = _validated_result_counts(
            model_request_count=model_request_count,
            tool_call_requested_count=tool_call_requested_count,
            tool_call_admitted_count=tool_call_admitted_count,
            tool_call_started_count=tool_call_started_count,
            tool_call_completed_count=tool_call_completed_count,
        )
        validated_usage = _validated_result_usage(usage, model_request_count)
        detached_transcript = _validated_result_transcript(transcript)

        object.__setattr__(self, "agent_key", identities["agent_key"])
        object.__setattr__(self, "name", identities["name"])
        object.__setattr__(self, "definition_id", identities["definition_id"])
        object.__setattr__(self, "structural_id", identities["structural_id"])
        object.__setattr__(self, "run_id", identities["run_id"])
        object.__setattr__(self, "output", output)
        object.__setattr__(self, "transcript", detached_transcript)
        object.__setattr__(self, "usage", validated_usage)
        for field, value in counts.items():
            object.__setattr__(self, field, value)
        object.__setattr__(self, "termination_reason", "final_output")


def _validated_result_identities(**identities: str) -> dict[str, str]:
    result = {
        field: require_ijson_text(value, field, nonempty=True)
        for field, value in identities.items()
    }
    if _AGENT_STRUCTURAL_ID.fullmatch(result["structural_id"]) is None:
        raise ValueError(
            "structural_id must use the agent_sha256:<64 lowercase hex> format."
        )
    return result


def _validated_result_counts(**counts: int) -> dict[str, int]:
    result = {
        field: require_ijson_integer(value, field, minimum=0)
        for field, value in counts.items()
    }
    if not (
        result["tool_call_completed_count"]
        <= result["tool_call_started_count"]
        <= result["tool_call_admitted_count"]
        <= result["tool_call_requested_count"]
    ):
        raise ValueError(
            "Tool counters must satisfy completed <= started <= admitted <= requested."
        )
    return result


def _validated_result_usage(usage: object, model_request_count: int) -> AgentUsage:
    if not isinstance(usage, AgentUsage):
        raise TypeError("usage must be AgentUsage.")
    if usage.model_responses > model_request_count:
        raise ValueError("usage.model_responses cannot exceed model_request_count.")
    return AgentUsage(model_responses=usage.model_responses, fields=usage.fields)


def _validated_result_transcript(
    transcript: Sequence[AgentMessage],
) -> tuple[AgentMessage, ...]:
    try:
        messages = tuple(transcript)
    except TypeError as exc:
        raise TypeError("transcript must be an iterable of AgentMessage values.") from exc
    if not messages:
        raise ValueError("A successful Agent transcript cannot be empty.")
    message_types = (
        AgentInputMessage,
        AssistantOutputMessage,
        AssistantToolCallsMessage,
        ToolResultMessage,
    )
    if any(not isinstance(item, message_types) for item in messages):
        raise TypeError("transcript must contain only AgentMessage values.")
    return validate_history(messages)
