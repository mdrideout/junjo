"""Provider-neutral immutable Agent messages, requests, responses, and usage."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal, TypeAlias

from .._json import (
    freeze_json,
    require_ijson_integer,
    require_ijson_text,
    thaw_json,
)
from .json import FrozenJsonValue


def _require_text(value: str, field: str) -> str:
    return require_ijson_text(value, field, nonempty=True)


@dataclass(frozen=True, slots=True, init=False)
class ModelUsage:
    """Optional provider-reported token facts for one validated model response."""

    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None
    reasoning_tokens: int | None
    total_tokens: int | None

    def __init__(
        self,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cached_input_tokens: int | None = None,
        reasoning_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> None:
        """Record optional nonnegative provider token facts.

        Omitted and reported-zero values remain distinct. Every supplied value
        must be a portable I-JSON integer.
        """
        values = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_input_tokens": cached_input_tokens,
            "reasoning_tokens": reasoning_tokens,
            "total_tokens": total_tokens,
        }
        for field, value in values.items():
            if value is not None:
                value = require_ijson_integer(value, field, minimum=0)
            object.__setattr__(self, field, value)

    def to_json(self) -> dict[str, int]:
        """Return the contract JSON shape, omitting unsupported facts."""

        result: dict[str, int] = {"v": 1}
        names = {
            "input_tokens": "inputTokens",
            "output_tokens": "outputTokens",
            "cached_input_tokens": "cachedInputTokens",
            "reasoning_tokens": "reasoningTokens",
            "total_tokens": "totalTokens",
        }
        for field, json_name in names.items():
            value = getattr(self, field)
            if value is not None:
                result[json_name] = value
        return result


@dataclass(frozen=True, slots=True, init=False)
class ToolCall:
    """One normalized model-requested Tool call."""

    id: str
    name: str
    arguments: Mapping[str, FrozenJsonValue]

    def __init__(self, *, id: str, name: str, arguments: Mapping[str, object]) -> None:
        """Create one detached model-requested Tool call.

        :param id: Nonempty run-scoped call identity.
        :param name: Declared Tool name.
        :param arguments: Portable JSON object awaiting Tool validation.
        """
        call_id = _require_text(id, "Tool call id")
        tool_name = _require_text(name, "Tool name")
        frozen = freeze_json(arguments)
        if not isinstance(frozen, Mapping):
            raise ValueError("Tool call arguments must be a JSON object.")
        freeze_json(
            {
                "id": call_id,
                "name": tool_name,
                "arguments": thaw_json(frozen),
            }
        )
        object.__setattr__(self, "id", call_id)
        object.__setattr__(self, "name", tool_name)
        object.__setattr__(self, "arguments", frozen)

    def to_json(self) -> dict[str, object]:
        return {"id": self.id, "name": self.name, "arguments": thaw_json(self.arguments)}


@dataclass(frozen=True, slots=True, init=False)
class AgentInputMessage:
    """One normalized application input message."""

    input: FrozenJsonValue
    type: ClassVar[Literal["agent_input"]] = "agent_input"

    def __init__(self, input: object) -> None:
        """Freeze one portable normalized application input value."""
        frozen = freeze_json(input)
        freeze_json({"type": self.type, "input": thaw_json(frozen)})
        object.__setattr__(self, "input", frozen)


@dataclass(frozen=True, slots=True, init=False)
class AssistantOutputMessage:
    """One normalized completed assistant output message."""

    output: FrozenJsonValue
    type: ClassVar[Literal["assistant_output"]] = "assistant_output"

    def __init__(self, output: object) -> None:
        """Freeze one portable validated assistant output value."""
        frozen = freeze_json(output)
        freeze_json({"type": self.type, "output": thaw_json(frozen)})
        object.__setattr__(self, "output", frozen)


@dataclass(frozen=True, slots=True, init=False)
class AssistantToolCallsMessage:
    """One normalized assistant decision containing ordered Tool calls."""

    tool_calls: tuple[ToolCall, ...]
    assistant_text: str | None
    type: ClassVar[Literal["assistant_tool_calls"]] = "assistant_tool_calls"

    def __init__(self, *, tool_calls: Sequence[ToolCall], assistant_text: str | None = None) -> None:
        """Create a nonempty ordered assistant Tool-call decision."""
        calls = tuple(tool_calls)
        if not calls:
            raise ValueError("AssistantToolCallsMessage requires at least one Tool call.")
        if any(not isinstance(call, ToolCall) for call in calls):
            raise TypeError("AssistantToolCallsMessage requires ToolCall values.")
        if assistant_text is not None:
            assistant_text = require_ijson_text(assistant_text, "assistant_text")
        message: dict[str, object] = {
            "type": self.type,
            "calls": [call.to_json() for call in calls],
        }
        if assistant_text is not None:
            message["assistantText"] = assistant_text
        freeze_json(message)
        object.__setattr__(self, "tool_calls", calls)
        object.__setattr__(self, "assistant_text", assistant_text)


@dataclass(frozen=True, slots=True, init=False)
class ToolResultMessage:
    """One normalized validated Tool result."""

    tool_call_id: str
    tool_name: str
    result: FrozenJsonValue
    type: ClassVar[Literal["tool_result"]] = "tool_result"

    def __init__(self, *, tool_call_id: str, tool_name: str, result: object) -> None:
        """Freeze one validated result matched to its declared Tool call."""
        call_id = _require_text(tool_call_id, "Tool call id")
        name = _require_text(tool_name, "Tool name")
        frozen = freeze_json(result)
        freeze_json(
            {
                "type": self.type,
                "callId": call_id,
                "toolName": name,
                "result": thaw_json(frozen),
            }
        )
        object.__setattr__(self, "tool_call_id", call_id)
        object.__setattr__(self, "tool_name", name)
        object.__setattr__(self, "result", frozen)


AgentMessage: TypeAlias = AgentInputMessage | AssistantOutputMessage | AssistantToolCallsMessage | ToolResultMessage


def message_to_json(message: AgentMessage) -> dict[str, object]:
    if isinstance(message, AgentInputMessage):
        return {"type": message.type, "input": thaw_json(message.input)}
    if isinstance(message, AssistantOutputMessage):
        return {"type": message.type, "output": thaw_json(message.output)}
    if isinstance(message, AssistantToolCallsMessage):
        result: dict[str, object] = {
            "type": message.type,
            "calls": [call.to_json() for call in message.tool_calls],
        }
        if message.assistant_text is not None:
            result["assistantText"] = message.assistant_text
        return result
    return {
        "type": message.type,
        "callId": message.tool_call_id,
        "toolName": message.tool_name,
        "result": thaw_json(message.result),
    }


def detach_message(message: AgentMessage) -> AgentMessage:
    """Return a structurally independent immutable message."""

    if isinstance(message, AgentInputMessage):
        return AgentInputMessage(thaw_json(message.input))
    if isinstance(message, AssistantOutputMessage):
        return AssistantOutputMessage(thaw_json(message.output))
    if isinstance(message, AssistantToolCallsMessage):
        return AssistantToolCallsMessage(
            assistant_text=message.assistant_text,
            tool_calls=[ToolCall(id=call.id, name=call.name, arguments=call.arguments) for call in message.tool_calls],
        )
    return ToolResultMessage(
        tool_call_id=message.tool_call_id,
        tool_name=message.tool_name,
        result=thaw_json(message.result),
    )


def validate_history(history: Sequence[AgentMessage]) -> tuple[AgentMessage, ...]:
    """Validate and detach zero or more complete Agent exchanges."""

    messages = tuple(history)
    detached: list[AgentMessage] = []
    seen_call_ids: set[str] = set()
    index = 0
    while index < len(messages):
        current = messages[index]
        if not isinstance(current, AgentInputMessage):
            raise ValueError("Each history exchange must begin with AgentInputMessage.")
        detached.append(detach_message(current))
        index += 1

        while index < len(messages) and isinstance(messages[index], AssistantToolCallsMessage):
            calls_message = messages[index]
            assert isinstance(calls_message, AssistantToolCallsMessage)
            for call in calls_message.tool_calls:
                if call.id in seen_call_ids:
                    raise ValueError(f"Duplicate Tool call id in history: {call.id}")
                seen_call_ids.add(call.id)
            detached.append(detach_message(calls_message))
            index += 1
            for expected in calls_message.tool_calls:
                if index >= len(messages) or not isinstance(messages[index], ToolResultMessage):
                    raise ValueError("Every historical Tool call requires one ordered ToolResultMessage.")
                result = messages[index]
                assert isinstance(result, ToolResultMessage)
                if result.tool_call_id != expected.id or result.tool_name != expected.name:
                    raise ValueError("Historical Tool results must match declared calls in order.")
                detached.append(detach_message(result))
                index += 1

        if index >= len(messages) or not isinstance(messages[index], AssistantOutputMessage):
            raise ValueError("Each history exchange must end with AssistantOutputMessage.")
        detached.append(detach_message(messages[index]))
        index += 1

    return tuple(detached)


@dataclass(frozen=True, slots=True, init=False)
class ToolDefinition:
    name: str
    description: str
    input_schema: Mapping[str, FrozenJsonValue]
    output_schema: Mapping[str, FrozenJsonValue]

    def __init__(
        self,
        *,
        name: str,
        description: str,
        input_schema: Mapping[str, object],
        output_schema: Mapping[str, object],
    ) -> None:
        """Create an immutable model-facing Tool definition snapshot."""
        object.__setattr__(self, "name", _require_text(name, "Tool name"))
        description = require_ijson_text(description, "Tool description")
        object.__setattr__(self, "description", description)
        frozen_input = freeze_json(input_schema)
        frozen_output = freeze_json(output_schema)
        if not isinstance(frozen_input, Mapping) or not isinstance(frozen_output, Mapping):
            raise ValueError("Tool schemas must be JSON objects.")
        freeze_json(
            {
                "name": self.name,
                "description": description,
                "inputSchema": thaw_json(frozen_input),
                "outputSchema": thaw_json(frozen_output),
            }
        )
        object.__setattr__(self, "input_schema", frozen_input)
        object.__setattr__(self, "output_schema", frozen_output)

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": thaw_json(self.input_schema),
            "outputSchema": thaw_json(self.output_schema),
        }


@dataclass(frozen=True, slots=True, init=False)
class ModelRequest:
    """Immutable normalized intent for one ModelDriver operation."""

    agent_key: str
    run_id: str
    ordinal: int
    instructions: str
    messages: tuple[AgentMessage, ...]
    tools: tuple[ToolDefinition, ...]
    output_schema: FrozenJsonValue

    def __init__(
        self,
        *,
        agent_key: str,
        run_id: str,
        ordinal: int,
        instructions: str,
        messages: Sequence[AgentMessage],
        tools: Sequence[ToolDefinition],
        output_schema: Mapping[str, object],
    ) -> None:
        """Create one immutable provider-neutral model request.

        :param agent_key: Stable semantic Agent key.
        :param run_id: Nonempty current Agent run identity.
        :param ordinal: Positive, contiguous model-request ordinal.
        :param instructions: Exact declared Agent instructions.
        :param messages: Detached normalized history plus current transcript.
        :param tools: Unique ordered Tool definitions.
        :param output_schema: Portable normalized output schema.
        :raises TypeError: If messages or Tools contain the wrong types.
        :raises ValueError: If identity, ordinal, schemas, or Tool uniqueness
            are invalid.
        """
        object.__setattr__(self, "agent_key", _require_text(agent_key, "Agent key"))
        object.__setattr__(self, "run_id", _require_text(run_id, "run_id"))
        ordinal = require_ijson_integer(ordinal, "ordinal", minimum=1)
        instructions = require_ijson_text(instructions, "instructions")
        declared_messages = tuple(messages)
        message_types = (
            AgentInputMessage,
            AssistantOutputMessage,
            AssistantToolCallsMessage,
            ToolResultMessage,
        )
        if any(not isinstance(message, message_types) for message in declared_messages):
            raise TypeError("messages must contain only AgentMessage values.")
        declared_tools = tuple(tools)
        if any(not isinstance(tool, ToolDefinition) for tool in declared_tools):
            raise TypeError("tools must contain only ToolDefinition values.")
        tool_names = [tool.name for tool in declared_tools]
        if len(tool_names) != len(set(tool_names)):
            raise ValueError("Tool names must be unique within a ModelRequest.")
        frozen_schema = freeze_json(output_schema)
        if not isinstance(frozen_schema, Mapping):
            raise ValueError("output_schema must be a JSON object.")
        object.__setattr__(self, "ordinal", ordinal)
        object.__setattr__(self, "instructions", instructions)
        object.__setattr__(
            self,
            "messages",
            tuple(detach_message(message) for message in declared_messages),
        )
        object.__setattr__(
            self,
            "tools",
            tuple(
                ToolDefinition(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                    output_schema=tool.output_schema,
                )
                for tool in declared_tools
            ),
        )
        object.__setattr__(self, "output_schema", frozen_schema)
        freeze_json(self.to_json())

    def to_json(self) -> dict[str, object]:
        return {
            "v": 1,
            "agentKey": self.agent_key,
            "runId": self.run_id,
            "ordinal": self.ordinal,
            "instructions": self.instructions,
            "messages": [message_to_json(message) for message in self.messages],
            "tools": [tool.to_json() for tool in self.tools],
            "outputSchema": thaw_json(self.output_schema),
        }


@dataclass(frozen=True, slots=True, init=False)
class FinalOutputResponse:
    """A normalized model response containing a final output candidate."""

    output: FrozenJsonValue
    usage: ModelUsage | None
    type: ClassVar[Literal["final_output"]] = "final_output"

    def __init__(self, *, output: object, usage: ModelUsage | None = None) -> None:
        """Create a portable final-output candidate and optional usage."""
        if usage is not None and not isinstance(usage, ModelUsage):
            raise TypeError("usage must be ModelUsage or None.")
        frozen = freeze_json(output)
        response: dict[str, object] = {
            "v": 1,
            "type": self.type,
            "output": thaw_json(frozen),
        }
        if usage is not None:
            response["usage"] = usage.to_json()
        freeze_json(response)
        object.__setattr__(self, "output", frozen)
        object.__setattr__(self, "usage", usage)


@dataclass(frozen=True, slots=True, init=False)
class ToolCallsResponse:
    """A normalized model response containing an ordered Tool-call batch."""

    tool_calls: tuple[ToolCall, ...]
    assistant_text: str | None
    usage: ModelUsage | None
    type: ClassVar[Literal["tool_calls"]] = "tool_calls"

    def __init__(
        self,
        *,
        tool_calls: Sequence[ToolCall],
        assistant_text: str | None = None,
        usage: ModelUsage | None = None,
    ) -> None:
        """Create a nonempty ordered Tool-call response and optional usage."""
        calls = tuple(tool_calls)
        if not calls:
            raise ValueError("ToolCallsResponse requires at least one Tool call.")
        if any(not isinstance(call, ToolCall) for call in calls):
            raise TypeError("ToolCallsResponse requires ToolCall values.")
        if assistant_text is not None:
            assistant_text = require_ijson_text(assistant_text, "assistant_text")
        if usage is not None and not isinstance(usage, ModelUsage):
            raise TypeError("usage must be ModelUsage or None.")
        response: dict[str, object] = {
            "v": 1,
            "type": self.type,
            "calls": [call.to_json() for call in calls],
        }
        if assistant_text is not None:
            response["assistantText"] = assistant_text
        if usage is not None:
            response["usage"] = usage.to_json()
        freeze_json(response)
        object.__setattr__(self, "tool_calls", calls)
        object.__setattr__(self, "assistant_text", assistant_text)
        object.__setattr__(self, "usage", usage)


ModelResponse: TypeAlias = FinalOutputResponse | ToolCallsResponse


def response_to_json(response: ModelResponse) -> dict[str, object]:
    result: dict[str, object]
    if isinstance(response, FinalOutputResponse):
        result = {
            "v": 1,
            "type": response.type,
            "output": thaw_json(response.output),
        }
    else:
        result = {
            "v": 1,
            "type": response.type,
            "calls": [call.to_json() for call in response.tool_calls],
        }
        if response.assistant_text is not None:
            result["assistantText"] = response.assistant_text
    if response.usage is not None:
        result["usage"] = response.usage.to_json()
    return result


def normalize_model_response(candidate: object) -> ModelResponse:
    """Validate one returned normalized response as an exact disjoint union."""

    if isinstance(candidate, FinalOutputResponse):
        return FinalOutputResponse(output=thaw_json(candidate.output), usage=candidate.usage)
    if isinstance(candidate, ToolCallsResponse):
        calls = tuple(ToolCall(id=call.id, name=call.name, arguments=call.arguments) for call in candidate.tool_calls)
        if len({call.id for call in calls}) != len(calls):
            raise ValueError("Tool call ids must be unique within a model response.")
        return ToolCallsResponse(
            tool_calls=calls,
            assistant_text=candidate.assistant_text,
            usage=candidate.usage,
        )
    mapping = _string_object_mapping(
        candidate,
        "Model response must be FinalOutputResponse, ToolCallsResponse, or an object.",
    )
    if not _is_version_one(mapping.get("v")):
        raise ValueError("Model response v must be 1.")
    if mapping.get("type") == "final_output":
        return _parse_final_output_mapping(mapping)
    if mapping.get("type") == "tool_calls":
        return _parse_tool_calls_mapping(mapping)
    raise ValueError("Model response type must be final_output or tool_calls.")


def _parse_final_output_mapping(candidate: Mapping[str, object]) -> FinalOutputResponse:
    if set(candidate) - {"v", "type", "output", "usage"}:
        raise ValueError("Final output response contains unexpected properties.")
    if "output" not in candidate or "calls" in candidate:
        raise ValueError("Final output response requires output and cannot contain calls.")
    usage = _usage_from_value(candidate["usage"]) if "usage" in candidate else None
    return FinalOutputResponse(output=candidate["output"], usage=usage)


def _parse_tool_calls_mapping(candidate: Mapping[str, object]) -> ToolCallsResponse:
    if set(candidate) - {"v", "type", "calls", "assistantText", "usage"}:
        raise ValueError("Tool calls response contains unexpected properties.")
    if "calls" not in candidate or "output" in candidate:
        raise ValueError("Tool calls response requires calls and cannot contain output.")
    raw_calls = candidate["calls"]
    if not isinstance(raw_calls, Sequence) or isinstance(raw_calls, str | bytes) or not raw_calls:
        raise ValueError("calls must be a non-empty sequence.")
    calls = tuple(_parse_tool_call_mapping(raw_call) for raw_call in raw_calls)
    call_ids = [call.id for call in calls]
    if len(call_ids) != len(set(call_ids)):
        raise ValueError("Tool call ids must be unique within a model response.")
    assistant_text = candidate.get("assistantText")
    if assistant_text is not None:
        assistant_text = require_ijson_text(assistant_text, "assistantText")
    usage = _usage_from_value(candidate["usage"]) if "usage" in candidate else None
    return ToolCallsResponse(tool_calls=calls, assistant_text=assistant_text, usage=usage)


def _parse_tool_call_mapping(value: object) -> ToolCall:
    mapping = _string_object_mapping(
        value,
        "Tool call must be an object with string property names.",
    )
    if set(mapping) != {"id", "name", "arguments"}:
        raise ValueError("Tool call must contain exactly id, name, and arguments.")
    call_id = mapping["id"]
    name = mapping["name"]
    arguments = mapping["arguments"]
    if not isinstance(call_id, str) or not isinstance(name, str):
        raise ValueError("Tool call id and name must be strings.")
    argument_mapping = _string_object_mapping(
        arguments,
        "Tool call arguments must be an object with string property names.",
    )
    return ToolCall(id=call_id, name=name, arguments=argument_mapping)


def _usage_from_value(value: object) -> ModelUsage:
    if isinstance(value, ModelUsage):
        return value
    mapping = _string_object_mapping(value, "usage must be a ModelUsage or object.")
    allowed = {
        "v",
        "inputTokens",
        "outputTokens",
        "cachedInputTokens",
        "reasoningTokens",
        "totalTokens",
    }
    if not _is_version_one(mapping.get("v")) or set(mapping) - allowed:
        raise ValueError("usage must match the closed model-usage v1 contract.")
    return ModelUsage(
        input_tokens=_optional_int(mapping, "inputTokens"),
        output_tokens=_optional_int(mapping, "outputTokens"),
        cached_input_tokens=_optional_int(mapping, "cachedInputTokens"),
        reasoning_tokens=_optional_int(mapping, "reasoningTokens"),
        total_tokens=_optional_int(mapping, "totalTokens"),
    )


def _string_object_mapping(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(message)
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(message)
        require_ijson_text(key, "JSON object key")
        result[key] = item
    return result


def _optional_int(mapping: Mapping[str, object], key: str) -> int | None:
    if key not in mapping:
        return None
    value = mapping[key]
    return require_ijson_integer(value, key, minimum=0)


def _is_version_one(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 1
