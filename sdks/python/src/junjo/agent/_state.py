"""Private typed Agent run state and explicit transition actions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from pydantic import JsonValue

from .._json import freeze_json, thaw_json
from ..state import BaseState
from ..store import BaseStore
from .messages import (
    AssistantToolCallsMessage,
    ModelResponse,
    ToolCallsResponse,
    message_to_json,
)
from .result import AgentUsage, UsageAggregateField
from .state import AgentStateSnapshot


class AgentState(BaseState):
    """Private JSON projection of one admitted Agent execution."""

    input: JsonValue
    history: list[JsonValue]
    transcript: list[JsonValue]
    model_iteration: int = 0
    model_request_count: int = 0
    tool_call_requested_count: int = 0
    tool_call_admitted_count: int = 0
    tool_call_started_count: int = 0
    tool_call_completed_count: int = 0
    usage: dict[str, JsonValue]
    admitted_tool_call_ids: list[str]
    pending_tool_call_ids: list[str]
    completed_tool_call_ids: list[str]
    final_output_available: bool = False
    final_output: JsonValue = None
    terminal_reason: str | None = None


class AgentStore(BaseStore[AgentState]):
    """Own every mutation of one private Agent run state."""

    def _get_last_known_state(self) -> AgentState:
        """Return the latest committed state without relying on an async read.

        Agent execution is sequential and this private Store is owned by one
        run.  The runtime uses this snapshot only as emergency diagnostic
        evidence after an admitted Store operation itself has failed.
        """

        return self._state.model_copy(deep=True)

    async def record_model_start(self, ordinal: int) -> int:
        """Commit model-start bookkeeping and return its revision.

        The private Agent Store has no lifecycle dispatcher and one sequential
        runtime owner. Reading the tracker synchronously after ``set_state``
        therefore forms one no-await-after-commit receipt for operation
        telemetry publication.
        """

        await self.set_state(
            {
                "model_iteration": ordinal,
                "model_request_count": ordinal,
            }
        )
        return self._telemetry_evidence.revision

    async def record_model_response(
        self,
        response: ModelResponse,
        usage: AgentUsage,
    ) -> None:
        snapshot = await self.get_state()
        await self.set_state(self._model_response_update(snapshot, response, usage))

    async def validate_model_response(
        self,
        response: ModelResponse,
        usage: AgentUsage,
    ) -> None:
        """Preflight the exact response state and RFC 6902 patch envelopes."""

        snapshot = await self.get_state()
        await self._validate_state_update(self._model_response_update(snapshot, response, usage))

    @staticmethod
    def _model_response_update(
        snapshot: AgentState,
        response: ModelResponse,
        usage: AgentUsage,
    ) -> dict[str, object]:
        transcript = list(snapshot.transcript)
        if isinstance(response, ToolCallsResponse):
            transcript.append(
                thaw_json(
                    freeze_json(
                        message_to_json(
                            AssistantToolCallsMessage(
                                tool_calls=response.tool_calls,
                                assistant_text=response.assistant_text,
                            )
                        )
                    )
                )
            )
            requested_count = snapshot.tool_call_requested_count + len(response.tool_calls)
        else:
            requested_count = snapshot.tool_call_requested_count
        return {
            "transcript": transcript,
            "tool_call_requested_count": requested_count,
            "usage": usage.to_json(),
        }

    async def admit_tool_batch(self, call_ids: Sequence[str]) -> None:
        snapshot = await self.get_state()
        await self.set_state(
            {
                "tool_call_admitted_count": (snapshot.tool_call_admitted_count + len(call_ids)),
                "admitted_tool_call_ids": [
                    *snapshot.admitted_tool_call_ids,
                    *call_ids,
                ],
                "pending_tool_call_ids": [*snapshot.pending_tool_call_ids, *call_ids],
            }
        )

    async def record_tool_started(self) -> int:
        """Commit Tool-start bookkeeping and return the pre-start revision."""

        snapshot = await self.get_state()
        revision_before = self._telemetry_evidence.revision
        await self.set_state({"tool_call_started_count": snapshot.tool_call_started_count + 1})
        return revision_before

    async def record_tool_result(
        self,
        *,
        call_id: str,
        tool_name: str,
        result: JsonValue,
    ) -> int:
        """Commit one Tool result and return its committed Store revision."""

        snapshot = await self.get_state()
        await self.set_state(
            self._tool_result_update(
                snapshot,
                call_id=call_id,
                tool_name=tool_name,
                result=result,
            )
        )
        return self._telemetry_evidence.revision

    async def validate_tool_result(
        self,
        *,
        call_id: str,
        tool_name: str,
        result: JsonValue,
    ) -> None:
        """Preflight the exact Tool-result state and patch envelopes."""

        snapshot = await self.get_state()
        await self._validate_state_update(
            self._tool_result_update(
                snapshot,
                call_id=call_id,
                tool_name=tool_name,
                result=result,
            )
        )

    @staticmethod
    def _tool_result_update(
        snapshot: AgentState,
        *,
        call_id: str,
        tool_name: str,
        result: JsonValue,
    ) -> dict[str, object]:
        pending = list(snapshot.pending_tool_call_ids)
        pending.remove(call_id)
        transcript = [
            *snapshot.transcript,
            thaw_json(
                freeze_json(
                    {
                        "type": "tool_result",
                        "callId": call_id,
                        "toolName": tool_name,
                        "result": result,
                    }
                )
            ),
        ]
        return {
            "transcript": transcript,
            "pending_tool_call_ids": pending,
            "completed_tool_call_ids": [
                *snapshot.completed_tool_call_ids,
                call_id,
            ],
            "tool_call_completed_count": snapshot.tool_call_completed_count + 1,
        }

    async def commit_success(self, output: JsonValue) -> None:
        """Atomically commit validated output and the successful terminal reason."""

        snapshot = await self.get_state()
        await self.set_state(self._success_update(snapshot, output))

    async def validate_success(self, output: JsonValue) -> None:
        """Preflight the exact success state and RFC 6902 patch envelopes."""

        snapshot = await self.get_state()
        await self._validate_state_update(self._success_update(snapshot, output))

    @staticmethod
    def _success_update(snapshot: AgentState, output: JsonValue) -> dict[str, object]:
        return {
            "transcript": [
                *snapshot.transcript,
                thaw_json(freeze_json({"type": "assistant_output", "output": output})),
            ],
            "final_output_available": True,
            "final_output": output,
            "terminal_reason": "final_output",
        }

    async def set_terminal_reason(self, reason: str) -> None:
        await self.set_state({"terminal_reason": reason})


def initial_agent_state(
    *,
    normalized_input: JsonValue,
    history: Sequence[JsonValue],
    transcript: Sequence[JsonValue],
) -> AgentState:
    """Construct a fresh private state for one admitted execution."""

    return AgentState(
        input=normalized_input,
        history=list(history),
        transcript=list(transcript),
        usage={"v": 1, "modelResponses": 0, "fields": {}},
        admitted_tool_call_ids=[],
        pending_tool_call_ids=[],
        completed_tool_call_ids=[],
    )


def snapshot_agent_state(state: AgentState) -> AgentStateSnapshot:
    """Detach private Store state into the public immutable diagnostic contract."""

    usage_json = state.usage
    raw_fields = usage_json.get("fields", {})
    if not isinstance(raw_fields, Mapping):
        raise TypeError("Private Agent usage fields must be an object.")
    fields: dict[str, UsageAggregateField] = {}
    for name, raw_field in raw_fields.items():
        if not isinstance(name, str) or not isinstance(raw_field, Mapping):
            raise TypeError("Private Agent usage fields are malformed.")
        field_mapping = cast(Mapping[str, object], raw_field)
        fields[name] = UsageAggregateField(
            sum=cast(int, field_mapping.get("sum")),
            observations=cast(int, field_mapping.get("observations")),
        )
    usage = AgentUsage(
        model_responses=cast(int, usage_json.get("modelResponses")),
        fields=fields,
    )
    return AgentStateSnapshot(
        input=state.input,
        history=state.history,
        transcript=state.transcript,
        model_iteration=state.model_iteration,
        model_request_count=state.model_request_count,
        tool_call_requested_count=state.tool_call_requested_count,
        tool_call_admitted_count=state.tool_call_admitted_count,
        tool_call_started_count=state.tool_call_started_count,
        tool_call_completed_count=state.tool_call_completed_count,
        usage=usage,
        admitted_tool_call_ids=state.admitted_tool_call_ids,
        pending_tool_call_ids=state.pending_tool_call_ids,
        completed_tool_call_ids=state.completed_tool_call_ids,
        final_output_available=state.final_output_available,
        final_output=state.final_output,
        terminal_reason=state.terminal_reason,
    )
