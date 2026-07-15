"""Public immutable diagnostic state for admitted Agent executions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .._json import (
    freeze_json,
    require_ijson_integer,
    require_ijson_text,
    thaw_json,
)
from .json import FrozenJsonValue, JsonValue
from .result import AgentUsage


@dataclass(frozen=True, slots=True, init=False)
class AgentStateSnapshot:
    """Detached state evidence exposed by admitted failures and cancellation.

    Snapshots contain only portable immutable JSON, immutable usage facts, and
    validated counters. They never expose the private mutable ``AgentStore``
    state object used by the execution kernel.
    """

    input: FrozenJsonValue
    history: tuple[FrozenJsonValue, ...]
    transcript: tuple[FrozenJsonValue, ...]
    model_iteration: int
    model_request_count: int
    tool_call_requested_count: int
    tool_call_admitted_count: int
    tool_call_started_count: int
    tool_call_completed_count: int
    usage: AgentUsage
    admitted_tool_call_ids: tuple[str, ...]
    pending_tool_call_ids: tuple[str, ...]
    completed_tool_call_ids: tuple[str, ...]
    final_output_available: bool
    final_output: FrozenJsonValue
    terminal_reason: str | None

    def __init__(
        self,
        *,
        input: object,
        history: Sequence[object],
        transcript: Sequence[object],
        model_iteration: int,
        model_request_count: int,
        tool_call_requested_count: int,
        tool_call_admitted_count: int,
        tool_call_started_count: int,
        tool_call_completed_count: int,
        usage: AgentUsage,
        admitted_tool_call_ids: Sequence[str],
        pending_tool_call_ids: Sequence[str],
        completed_tool_call_ids: Sequence[str],
        final_output_available: bool,
        final_output: object,
        terminal_reason: str | None,
    ) -> None:
        """Create detached immutable evidence for one admitted execution.

        Every JSON value is copied and frozen. Counters, usage, final-output
        availability, and admitted/pending/completed Tool identities are
        validated as one coherent snapshot.
        """
        counts = _validated_counts(
            model_iteration=model_iteration,
            model_request_count=model_request_count,
            tool_call_requested_count=tool_call_requested_count,
            tool_call_admitted_count=tool_call_admitted_count,
            tool_call_started_count=tool_call_started_count,
            tool_call_completed_count=tool_call_completed_count,
        )
        _validate_usage(usage, model_request_count)
        _validate_final_output_available(final_output_available)
        if terminal_reason is not None:
            terminal_reason = require_ijson_text(terminal_reason, "terminal_reason", nonempty=True)

        admitted = _owned_ids(admitted_tool_call_ids, "admitted_tool_call_ids")
        pending = _owned_ids(pending_tool_call_ids, "pending_tool_call_ids")
        completed = _owned_ids(completed_tool_call_ids, "completed_tool_call_ids")
        _validate_tool_ids(
            admitted=admitted,
            pending=pending,
            completed=completed,
            admitted_count=tool_call_admitted_count,
            completed_count=tool_call_completed_count,
        )

        object.__setattr__(self, "input", freeze_json(input))
        object.__setattr__(self, "history", tuple(freeze_json(item) for item in history))
        object.__setattr__(self, "transcript", tuple(freeze_json(item) for item in transcript))
        for name, value in counts.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "usage", usage)
        object.__setattr__(self, "admitted_tool_call_ids", admitted)
        object.__setattr__(self, "pending_tool_call_ids", pending)
        object.__setattr__(self, "completed_tool_call_ids", completed)
        object.__setattr__(self, "final_output_available", final_output_available)
        object.__setattr__(self, "final_output", freeze_json(final_output))
        object.__setattr__(self, "terminal_reason", terminal_reason)
        freeze_json(self.to_json())

    def to_json(self) -> dict[str, JsonValue]:
        """Return a detached contract projection suitable for telemetry/evals."""

        return {
            "input": thaw_json(self.input),
            "history": [thaw_json(item) for item in self.history],
            "transcript": [thaw_json(item) for item in self.transcript],
            "model_iteration": self.model_iteration,
            "model_request_count": self.model_request_count,
            "tool_call_requested_count": self.tool_call_requested_count,
            "tool_call_admitted_count": self.tool_call_admitted_count,
            "tool_call_started_count": self.tool_call_started_count,
            "tool_call_completed_count": self.tool_call_completed_count,
            "usage": self.usage.to_json(),
            "admitted_tool_call_ids": list(self.admitted_tool_call_ids),
            "pending_tool_call_ids": list(self.pending_tool_call_ids),
            "completed_tool_call_ids": list(self.completed_tool_call_ids),
            "final_output_available": self.final_output_available,
            "final_output": thaw_json(self.final_output),
            "terminal_reason": self.terminal_reason,
        }


def _owned_ids(values: Sequence[str], name: str) -> tuple[str, ...]:
    result = tuple(require_ijson_text(value, name, nonempty=True) for value in values)
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must contain unique values.")
    return result


def _validated_counts(**counts: int) -> dict[str, int]:
    for name, value in counts.items():
        require_ijson_integer(value, name, minimum=0)
    if counts["model_iteration"] != counts["model_request_count"]:
        raise ValueError("model_iteration must equal model_request_count.")
    if not (
        counts["tool_call_completed_count"]
        <= counts["tool_call_started_count"]
        <= counts["tool_call_admitted_count"]
        <= counts["tool_call_requested_count"]
    ):
        raise ValueError("Tool counters must satisfy completed <= started <= admitted <= requested.")
    return counts


def _validate_usage(usage: object, model_request_count: int) -> None:
    if not isinstance(usage, AgentUsage):
        raise TypeError("usage must be AgentUsage.")
    if usage.model_responses > model_request_count:
        raise ValueError("usage.model_responses cannot exceed model_request_count.")


def _validate_final_output_available(value: object) -> None:
    if not isinstance(value, bool):
        raise TypeError("final_output_available must be bool.")


def _validate_tool_ids(
    *,
    admitted: tuple[str, ...],
    pending: tuple[str, ...],
    completed: tuple[str, ...],
    admitted_count: int,
    completed_count: int,
) -> None:
    if len(admitted) != admitted_count:
        raise ValueError("admitted_tool_call_ids must match tool_call_admitted_count.")
    if len(completed) != completed_count:
        raise ValueError("completed_tool_call_ids must match tool_call_completed_count.")
    if set(pending) | set(completed) != set(admitted):
        raise ValueError("Pending and completed Tool ids must partition admitted Tool ids.")
    if set(pending) & set(completed):
        raise ValueError("Pending and completed Tool ids must be disjoint.")
