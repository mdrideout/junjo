"""OpenAI Agents source-span mapping and complete JSON-safe serialization."""

from __future__ import annotations

import base64
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any, cast

from agents.tracing import Span as OpenAISpan
from agents.tracing import Trace as OpenAITrace
from agents.tracing.span_data import (
    AgentSpanData,
    CustomSpanData,
    FunctionSpanData,
    GenerationSpanData,
    GuardrailSpanData,
    HandoffSpanData,
    MCPListToolsSpanData,
    ResponseSpanData,
    SpanData,
    SpeechGroupSpanData,
    SpeechSpanData,
    TaskSpanData,
    TranscriptionSpanData,
    TurnSpanData,
)

SCHEMA_VERSION = 1
SCHEMA_VERSION_ATTRIBUTE = "junjo.openai_agents.schema_version"
SPAN_TYPE_ATTRIBUTE = "junjo.openai_agents.span.type"
SOURCE_TRACE_ID_ATTRIBUTE = "junjo.openai_agents.source.trace_id"
SOURCE_SPAN_ID_ATTRIBUTE = "junjo.openai_agents.source.span_id"
SOURCE_PARENT_SPAN_ID_ATTRIBUTE = "junjo.openai_agents.source.parent_span_id"
SPAN_DATA_ATTRIBUTE = "junjo.openai_agents.span.data"
TRACE_ID_ATTRIBUTE = "junjo.openai_agents.trace.id"
TRACE_DATA_ATTRIBUTE = "junjo.openai_agents.trace.data"
TRANSLATION_ERROR_TYPE_ATTRIBUTE = "junjo.openai_agents.translation.error.type"
TRANSLATION_ERROR_MESSAGE_ATTRIBUTE = "junjo.openai_agents.translation.error.message"

SUPPORTED_SPAN_DATA_CLASSES: frozenset[type[SpanData]] = frozenset(
    {
        AgentSpanData,
        CustomSpanData,
        FunctionSpanData,
        GenerationSpanData,
        GuardrailSpanData,
        HandoffSpanData,
        MCPListToolsSpanData,
        ResponseSpanData,
        SpeechGroupSpanData,
        SpeechSpanData,
        TaskSpanData,
        TranscriptionSpanData,
        TurnSpanData,
    }
)


@dataclass(frozen=True, slots=True)
class MappedSpanStart:
    """Small attributes needed before the source operation executes."""

    name: str
    source_type: str
    attributes: dict[str, str | int | float | bool]


def map_trace_start(trace: OpenAITrace) -> MappedSpanStart:
    """Map one OpenAI workflow Trace to its initial OpenTelemetry identity."""

    name = trace.name or "Agent workflow"
    return MappedSpanStart(
        name=f"invoke_workflow {name}",
        source_type="trace",
        attributes={
            SCHEMA_VERSION_ATTRIBUTE: SCHEMA_VERSION,
            TRACE_ID_ATTRIBUTE: trace.trace_id,
            "gen_ai.operation.name": "invoke_workflow",
            "gen_ai.workflow.name": name,
        },
    )


def map_span_start(span: OpenAISpan[Any]) -> MappedSpanStart:  # noqa: C901
    """Map one source Span to its initial name and queryable attributes."""

    data = span.span_data
    source_type = _source_type(data)
    attributes: dict[str, str | int | float | bool] = {
        SCHEMA_VERSION_ATTRIBUTE: SCHEMA_VERSION,
        SPAN_TYPE_ATTRIBUTE: source_type,
        SOURCE_TRACE_ID_ATTRIBUTE: span.trace_id,
        SOURCE_SPAN_ID_ATTRIBUTE: span.span_id,
    }
    if span.parent_id:
        attributes[SOURCE_PARENT_SPAN_ID_ATTRIBUTE] = span.parent_id

    if isinstance(data, AgentSpanData):
        attributes["gen_ai.operation.name"] = "invoke_agent"
        attributes["gen_ai.agent.name"] = data.name
        return MappedSpanStart(f"invoke_agent {data.name}", source_type, attributes)
    if isinstance(data, FunctionSpanData):
        attributes["gen_ai.operation.name"] = "execute_tool"
        attributes["gen_ai.tool.name"] = data.name
        attributes["gen_ai.tool.type"] = "function"
        return MappedSpanStart(f"execute_tool {data.name}", source_type, attributes)
    if isinstance(data, GenerationSpanData):
        attributes["gen_ai.operation.name"] = "chat"
        if data.model:
            attributes["gen_ai.request.model"] = data.model
        return MappedSpanStart(_model_span_name("chat", data.model), source_type, attributes)
    if isinstance(data, ResponseSpanData):
        attributes["gen_ai.operation.name"] = "chat"
        model = _response_model(data)
        if model:
            attributes["gen_ai.response.model"] = model
        return MappedSpanStart(_model_span_name("chat", model), source_type, attributes)
    if isinstance(data, HandoffSpanData):
        return MappedSpanStart(
            f"handoff {_text(data.from_agent, 'unknown')} to {_text(data.to_agent, 'unknown')}",
            source_type,
            attributes,
        )
    if isinstance(data, GuardrailSpanData):
        return MappedSpanStart(f"guardrail {data.name}", source_type, attributes)
    if isinstance(data, TaskSpanData):
        return MappedSpanStart(f"task {data.name}", source_type, attributes)
    if isinstance(data, TurnSpanData):
        return MappedSpanStart(f"turn {data.turn} {data.agent_name}", source_type, attributes)
    if isinstance(data, MCPListToolsSpanData):
        return MappedSpanStart(f"mcp.list_tools {_text(data.server, 'unknown')}", source_type, attributes)
    if isinstance(data, CustomSpanData):
        return MappedSpanStart(f"custom {data.name}", source_type, attributes)
    if isinstance(data, SpeechGroupSpanData):
        return MappedSpanStart("speech group", source_type, attributes)
    if isinstance(data, SpeechSpanData):
        return MappedSpanStart(_model_span_name("speech", data.model), source_type, attributes)
    if isinstance(data, TranscriptionSpanData):
        return MappedSpanStart(_model_span_name("transcription", data.model), source_type, attributes)

    return MappedSpanStart(f"openai_agents {source_type}", source_type, attributes)


def final_trace_attributes(
    trace: OpenAITrace,
    *,
    started_at: str,
    ended_at: str,
) -> dict[str, str | int | float | bool]:
    """Serialize the final workflow Trace payload exactly once."""

    payload = {
        "source_class": _qualified_name(trace),
        "trace_id": trace.trace_id,
        "name": trace.name,
        "group_id": getattr(trace, "group_id", None),
        "metadata": getattr(trace, "metadata", None),
        "started_at": started_at,
        "ended_at": ended_at,
        "tracing_api_key_configured": bool(trace.tracing_api_key),
    }
    return {TRACE_DATA_ATTRIBUTE: _json_payload(payload)}


def final_span_attributes(span: OpenAISpan[Any]) -> dict[str, str | int | float | bool]:
    """Serialize the final source Span and add small final semantic projections."""

    data = span.span_data
    payload = {
        "source_class": _qualified_name(data),
        "source_type": _source_type(data),
        "trace_id": span.trace_id,
        "span_id": span.span_id,
        "parent_span_id": span.parent_id,
        "started_at": span.started_at,
        "ended_at": span.ended_at,
        "trace_metadata": span.trace_metadata,
        "tracing_api_key_configured": bool(span.tracing_api_key),
        "data": _known_span_data(data),
        "error": span.error,
    }
    attributes: dict[str, str | int | float | bool] = {
        SPAN_DATA_ATTRIBUTE: _json_payload(payload)
    }

    model = _model(data)
    if isinstance(data, ResponseSpanData) and model:
        attributes["gen_ai.response.model"] = model
    elif isinstance(data, GenerationSpanData) and model:
        attributes["gen_ai.request.model"] = model

    usage = _usage(data)
    input_tokens = _integer_field(usage, "input_tokens")
    output_tokens = _integer_field(usage, "output_tokens")
    if input_tokens is not None:
        attributes["gen_ai.usage.input_tokens"] = input_tokens
    if output_tokens is not None:
        attributes["gen_ai.usage.output_tokens"] = output_tokens

    error_type = _error_type(span.error)
    if error_type:
        attributes["error.type"] = error_type
    return attributes


def source_span_error_message(span: OpenAISpan[Any]) -> str | None:
    """Return the source error message when it is safely available."""

    error = span.error
    if not isinstance(error, Mapping):
        return None
    message = error.get("message")
    return message if isinstance(message, str) and message else None


def json_safe(value: object) -> object:
    """Return a complete JSON-safe representation without truncating source data."""

    return _json_safe(value, active=set())


def _json_safe(value: object, *, active: set[int]) -> object:  # noqa: C901
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        if -(2**53 - 1) <= value <= 2**53 - 1:
            return value
        return {"__junjo_type": "integer", "value": str(value)}
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return {"__junjo_type": "float", "value": str(value)}
    if isinstance(value, bytes):
        return {
            "__junjo_type": "bytes",
            "encoding": "base64",
            "data": base64.b64encode(value).decode("ascii"),
        }
    if isinstance(value, bytearray):
        return _json_safe(bytes(value), active=active)
    if isinstance(value, memoryview):
        return _json_safe(value.tobytes(), active=active)
    if isinstance(value, Enum):
        return _json_safe(value.value, active=active)

    identity = id(value)
    if identity in active:
        return {"__junjo_type": "cycle", "class": _qualified_name(value)}

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        active.add(identity)
        try:
            dumped = cast(Callable[..., object], model_dump)(mode="json")
            return _json_safe(dumped, active=active)
        except Exception:
            pass
        finally:
            active.discard(identity)

    if is_dataclass(value) and not isinstance(value, type):
        active.add(identity)
        try:
            return {
                item.name: _json_safe(getattr(value, item.name), active=active)
                for item in fields(value)
            }
        finally:
            active.discard(identity)

    if isinstance(value, Mapping):
        active.add(identity)
        try:
            return {
                _mapping_key(key): _json_safe(item, active=active)
                for key, item in value.items()
            }
        finally:
            active.discard(identity)

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        active.add(identity)
        try:
            return [_json_safe(item, active=active) for item in value]
        finally:
            active.discard(identity)

    if isinstance(value, (set, frozenset)):
        active.add(identity)
        try:
            return [_json_safe(item, active=active) for item in sorted(value, key=_safe_repr)]
        finally:
            active.discard(identity)

    return _safe_repr(value)


def _known_span_data(data: SpanData) -> object:  # noqa: C901
    if isinstance(data, AgentSpanData):
        return {
            "name": data.name,
            "handoffs": data.handoffs,
            "tools": data.tools,
            "output_type": data.output_type,
            "metadata": data.metadata,
        }
    if isinstance(data, FunctionSpanData):
        return {
            "name": data.name,
            "input": data.input,
            "output": data.output,
            "mcp_data": data.mcp_data,
        }
    if isinstance(data, GenerationSpanData):
        return {
            "input": data.input,
            "output": data.output,
            "model": data.model,
            "model_config": data.model_config,
            "usage": data.usage,
        }
    if isinstance(data, ResponseSpanData):
        return {"input": data.input, "response": data.response, "usage": data.usage}
    if isinstance(data, HandoffSpanData):
        return {"from_agent": data.from_agent, "to_agent": data.to_agent}
    if isinstance(data, GuardrailSpanData):
        return {"name": data.name, "triggered": data.triggered}
    if isinstance(data, TaskSpanData):
        return {"name": data.name, "usage": data.usage, "metadata": data.metadata}
    if isinstance(data, TurnSpanData):
        return {
            "turn": data.turn,
            "agent_name": data.agent_name,
            "usage": data.usage,
            "metadata": data.metadata,
        }
    if isinstance(data, MCPListToolsSpanData):
        return {"server": data.server, "result": data.result}
    if isinstance(data, CustomSpanData):
        return {"name": data.name, "data": data.data}
    if isinstance(data, SpeechGroupSpanData):
        return {"input": data.input}
    if isinstance(data, SpeechSpanData):
        return {
            "input": data.input,
            "output": data.output,
            "output_format": data.output_format,
            "model": data.model,
            "model_config": data.model_config,
            "first_content_at": data.first_content_at,
        }
    if isinstance(data, TranscriptionSpanData):
        return {
            "input": data.input,
            "input_format": data.input_format,
            "output": data.output,
            "model": data.model,
            "model_config": data.model_config,
        }
    return {"export": _safe_export(data), "public_fields": _public_fields(data)}


def _safe_export(data: SpanData) -> object:
    try:
        return data.export()
    except Exception as error:
        return {
            "__junjo_type": "export_error",
            "error_type": type(error).__name__,
            "message": _safe_exception_text(error),
        }


def _public_fields(value: object) -> dict[str, object]:
    names: set[str] = set()
    dictionary = getattr(value, "__dict__", None)
    if isinstance(dictionary, dict):
        names.update(key for key in dictionary if not key.startswith("_"))
    for cls in type(value).__mro__:
        slots = getattr(cls, "__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        names.update(name for name in slots if isinstance(name, str) and not name.startswith("_"))
    result: dict[str, object] = {}
    for name in sorted(names):
        try:
            result[name] = getattr(value, name)
        except Exception as error:
            result[name] = {
                "__junjo_type": "field_error",
                "error_type": type(error).__name__,
                "message": _safe_exception_text(error),
            }
    return result


def _json_payload(value: object) -> str:
    return json.dumps(
        json_safe(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _source_type(data: SpanData) -> str:
    try:
        value = data.type
    except Exception:
        value = None
    return value if isinstance(value, str) and value else type(data).__name__


def _qualified_name(value: object) -> str:
    cls = type(value)
    return f"{cls.__module__}.{cls.__qualname__}"


def _mapping_key(value: object) -> str:
    return value if isinstance(value, str) else _safe_repr(value)


def _safe_repr(value: object) -> str:
    try:
        return repr(value)
    except Exception:
        return f"<{_qualified_name(value)} instance>"


def _safe_exception_text(error: BaseException) -> str:
    try:
        return str(error)
    except Exception:
        return type(error).__name__


def _text(value: object, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _model_span_name(operation: str, model: object) -> str:
    return f"{operation} {model}" if isinstance(model, str) and model else operation


def _response_model(data: ResponseSpanData) -> str | None:
    response = data.response
    model = getattr(response, "model", None) if response is not None else None
    return model if isinstance(model, str) and model else None


def _model(data: SpanData) -> str | None:
    if isinstance(data, ResponseSpanData):
        return _response_model(data)
    if isinstance(data, (GenerationSpanData, SpeechSpanData, TranscriptionSpanData)):
        return data.model if isinstance(data.model, str) and data.model else None
    return None


def _usage(data: SpanData) -> object:
    if isinstance(data, (GenerationSpanData, ResponseSpanData, TaskSpanData, TurnSpanData)):
        return data.usage
    return None


def _integer_field(value: object, key: str) -> int | None:
    candidate: object
    if isinstance(value, Mapping):
        candidate = cast(Mapping[object, object], value).get(key)
    else:
        candidate = getattr(value, key, None)
    return candidate if isinstance(candidate, int) and not isinstance(candidate, bool) else None


def _error_type(error: object) -> str | None:
    if not isinstance(error, Mapping):
        return None
    error_mapping = cast(Mapping[object, object], error)
    data = error_mapping.get("data")
    if isinstance(data, Mapping):
        name = cast(Mapping[object, object], data).get("name")
        if isinstance(name, str) and name:
            return name
    candidate = error_mapping.get("type")
    return candidate if isinstance(candidate, str) and candidate else None


__all__ = [
    "MappedSpanStart",
    "SCHEMA_VERSION",
    "SCHEMA_VERSION_ATTRIBUTE",
    "SOURCE_PARENT_SPAN_ID_ATTRIBUTE",
    "SOURCE_SPAN_ID_ATTRIBUTE",
    "SOURCE_TRACE_ID_ATTRIBUTE",
    "SPAN_DATA_ATTRIBUTE",
    "SPAN_TYPE_ATTRIBUTE",
    "SUPPORTED_SPAN_DATA_CLASSES",
    "TRACE_DATA_ATTRIBUTE",
    "TRACE_ID_ATTRIBUTE",
    "TRANSLATION_ERROR_MESSAGE_ATTRIBUTE",
    "TRANSLATION_ERROR_TYPE_ATTRIBUTE",
    "final_span_attributes",
    "final_trace_attributes",
    "json_safe",
    "map_span_start",
    "map_trace_start",
    "source_span_error_message",
]
