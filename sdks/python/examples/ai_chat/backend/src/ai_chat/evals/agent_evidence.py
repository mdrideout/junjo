"""Portable Agent Tool evidence used by application-owned live judges."""

from collections.abc import Mapping, Sequence
from typing import cast

from junjo.agent import (
    AgentMessage,
    AssistantToolCallsMessage,
    FrozenJsonValue,
    ToolResultMessage,
)


def tool_transcript_evidence(
    transcript: Sequence[AgentMessage],
) -> list[dict[str, object]]:
    """Project only Tool decisions and results through public Agent contracts."""

    evidence: list[dict[str, object]] = []
    for message in transcript:
        if isinstance(message, AssistantToolCallsMessage):
            evidence.append(
                {
                    "type": message.type,
                    "calls": [call.to_json() for call in message.tool_calls],
                }
            )
        elif isinstance(message, ToolResultMessage):
            evidence.append(
                {
                    "type": message.type,
                    "callId": message.tool_call_id,
                    "toolName": message.tool_name,
                    "result": _portable_json(message.result),
                }
            )
    return evidence


def _portable_json(value: FrozenJsonValue) -> object:
    if isinstance(value, Mapping):
        mapping = cast(Mapping[str, FrozenJsonValue], value)
        return {key: _portable_json(item) for key, item in mapping.items()}
    if isinstance(value, tuple):
        return [_portable_json(item) for item in value]
    return value
