import inspect
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import agents.tracing.span_data as openai_span_data
import pytest
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
from pydantic import BaseModel

from junjo.plugins.openai_agents._span_mapping import (
    SCHEMA_VERSION_ATTRIBUTE,
    SOURCE_PARENT_SPAN_ID_ATTRIBUTE,
    SOURCE_SPAN_ID_ATTRIBUTE,
    SOURCE_TRACE_ID_ATTRIBUTE,
    SPAN_DATA_ATTRIBUTE,
    SPAN_TYPE_ATTRIBUTE,
    SUPPORTED_SPAN_DATA_CLASSES,
    TRACE_DATA_ATTRIBUTE,
    TRACE_ID_ATTRIBUTE,
    TRANSLATION_ERROR_MESSAGE_ATTRIBUTE,
    TRANSLATION_ERROR_TYPE_ATTRIBUTE,
    final_span_attributes,
    json_safe,
    map_span_start,
)


class FakeResponse(BaseModel):
    id: str
    model: str
    output: list[dict[str, object]]
    usage: dict[str, int]


class FutureSpanData(SpanData):
    def __init__(self) -> None:
        self.detail = {"future": True}

    @property
    def type(self) -> str:
        return "future"

    def export(self) -> dict[str, object]:
        return {"type": self.type, "detail": self.detail}


def source_span(
    data: SpanData,
    *,
    error: object = None,
    tracing_api_key: str | None = None,
) -> Any:
    return SimpleNamespace(
        trace_id="trace_source",
        span_id="span_source",
        parent_id="span_parent",
        span_data=data,
        started_at="2026-08-23T12:00:00+00:00",
        ended_at="2026-08-23T12:00:01+00:00",
        trace_metadata={"experiment": "baseline"},
        tracing_api_key=tracing_api_key,
        error=error,
    )


@pytest.mark.parametrize(
    ("data", "source_type", "name", "operation"),
    [
        (
            AgentSpanData(
                name="Coordinator",
                handoffs=["Reviewer"],
                tools=["lookup"],
                output_type="str",
                metadata={"role": "outer"},
            ),
            "agent",
            "invoke_agent Coordinator",
            "invoke_agent",
        ),
        (
            FunctionSpanData(
                name="lookup",
                input='{"place":"Brooklyn"}',
                output={"name": "Prospect Park"},
                mcp_data={"server": "places"},
            ),
            "function",
            "execute_tool lookup",
            "execute_tool",
        ),
        (
            GenerationSpanData(
                input=[{"role": "user", "content": "Where?"}],
                output=[{"role": "assistant", "content": "Prospect Park"}],
                model="provider-model",
                model_config={"temperature": 0},
                usage={"input_tokens": 10, "output_tokens": 3},
            ),
            "generation",
            "chat provider-model",
            "chat",
        ),
        (
            ResponseSpanData(
                response=FakeResponse(
                    id="resp_1",
                    model="gpt-test",
                    output=[{"type": "message", "content": "Prospect Park"}],
                    usage={"input_tokens": 10, "output_tokens": 3},
                ),  # type: ignore[arg-type]
                input="Where?",
                usage={"input_tokens": 10, "output_tokens": 3},
            ),
            "response",
            "chat gpt-test",
            "chat",
        ),
        (
            HandoffSpanData(from_agent="Coordinator", to_agent="Reviewer"),
            "handoff",
            "handoff Coordinator to Reviewer",
            None,
        ),
        (GuardrailSpanData(name="realism", triggered=False), "guardrail", "guardrail realism", None),
        (
            TaskSpanData(name="Local places", usage={"requests": 2}, metadata={"run": "baseline"}),
            "task",
            "task Local places",
            None,
        ),
        (
            TurnSpanData(
                turn=2,
                agent_name="Coordinator",
                usage={"input_tokens": 7},
                metadata={"phase": "tools"},
            ),
            "turn",
            "turn 2 Coordinator",
            None,
        ),
        (MCPListToolsSpanData(server="places", result=["search"]), "mcp_tools", "mcp.list_tools places", None),
        (CustomSpanData(name="ranking", data={"top": "Prospect Park"}), "custom", "custom ranking", None),
        (SpeechGroupSpanData(input="Hello"), "speech_group", "speech group", None),
        (
            SpeechSpanData(
                input="Hello",
                output="encoded-audio",
                output_format="mp3",
                model="tts-test",
                model_config={"voice": "calm"},
                first_content_at="2026-08-23T12:00:00.2+00:00",
            ),
            "speech",
            "speech tts-test",
            None,
        ),
        (
            TranscriptionSpanData(
                input="encoded-audio",
                input_format="mp3",
                output="Hello",
                model="transcribe-test",
                model_config={"language": "en"},
            ),
            "transcription",
            "transcription transcribe-test",
            None,
        ),
    ],
)
def test_every_current_source_type_has_complete_payload_and_truthful_projection(
    data: SpanData,
    source_type: str,
    name: str,
    operation: str | None,
) -> None:
    span = source_span(data)

    start = map_span_start(span)
    final = final_span_attributes(span)
    payload = json.loads(final[SPAN_DATA_ATTRIBUTE])

    assert start.name == name
    assert start.source_type == source_type
    assert start.attributes[SCHEMA_VERSION_ATTRIBUTE] == 1
    assert start.attributes[SPAN_TYPE_ATTRIBUTE] == source_type
    assert start.attributes.get("gen_ai.operation.name") == operation
    assert payload["source_type"] == source_type
    assert payload["data"] is not None
    assert payload["trace_id"] == "trace_source"
    assert payload["span_id"] == "span_source"
    assert payload["parent_span_id"] == "span_parent"
    assert payload["tracing_api_key_configured"] is False
    assert "junjo.span_type" not in start.attributes
    assert "junjo.executable_runtime_id" not in start.attributes


def test_response_payload_keeps_complete_public_model_and_usage() -> None:
    data = ResponseSpanData(
        response=FakeResponse(
            id="resp_complete",
            model="gpt-complete",
            output=[{"type": "message", "content": "A complete response"}],
            usage={"input_tokens": 17, "output_tokens": 4},
        ),  # type: ignore[arg-type]
        input=[{"role": "user", "content": "Complete input"}],  # type: ignore[arg-type]
        usage={"input_tokens": 17, "output_tokens": 4},
    )

    attributes = final_span_attributes(source_span(data))
    payload = json.loads(attributes[SPAN_DATA_ATTRIBUTE])

    assert payload["data"]["input"][0]["content"] == "Complete input"
    assert payload["data"]["response"]["id"] == "resp_complete"
    assert payload["data"]["response"]["output"][0]["content"] == "A complete response"
    assert attributes["gen_ai.response.model"] == "gpt-complete"
    assert attributes["gen_ai.usage.input_tokens"] == 17
    assert attributes["gen_ai.usage.output_tokens"] == 4


def test_agent_and_task_metadata_omitted_by_source_export_are_retained() -> None:
    agent = AgentSpanData(name="Coordinator", metadata={"private_source_field": "retained"})
    task = TaskSpanData(name="Task", metadata={"experiment": "baseline"})

    agent_payload = json.loads(final_span_attributes(source_span(agent))[SPAN_DATA_ATTRIBUTE])
    task_payload = json.loads(final_span_attributes(source_span(task))[SPAN_DATA_ATTRIBUTE])

    assert "metadata" not in agent.export()
    assert agent_payload["data"]["metadata"] == {"private_source_field": "retained"}
    assert "metadata" not in task.export()["data"]
    assert task_payload["data"]["metadata"] == {"experiment": "baseline"}


def test_unknown_future_type_is_preserved_without_semantic_misclassification() -> None:
    span = source_span(FutureSpanData())

    start = map_span_start(span)
    payload = json.loads(final_span_attributes(span)[SPAN_DATA_ATTRIBUTE])

    assert start.name == "openai_agents future"
    assert "gen_ai.operation.name" not in start.attributes
    assert payload["source_class"].endswith("FutureSpanData")
    assert payload["data"]["export"] == {"type": "future", "detail": {"future": True}}
    assert payload["data"]["public_fields"] == {"detail": {"future": True}}


def test_coverage_sentinel_matches_every_concrete_locked_source_type() -> None:
    concrete = {
        candidate
        for _, candidate in inspect.getmembers(openai_span_data, inspect.isclass)
        if candidate.__module__ == openai_span_data.__name__
        and issubclass(candidate, SpanData)
        and candidate is not SpanData
        and not inspect.isabstract(candidate)
    }

    assert concrete == SUPPORTED_SPAN_DATA_CLASSES


def test_sdk_attribute_names_match_the_shared_integration_contract() -> None:
    repository_root = Path(__file__).resolve().parents[5]
    contract = json.loads(
        (
            repository_root
            / "contracts/telemetry/integrations/openai_agents/v1/attribute-names.json"
        ).read_text()
    )

    assert contract["schema_version"] == 1
    assert contract["attributes"] == {
        "schema_version": SCHEMA_VERSION_ATTRIBUTE,
        "source_parent_span_id": SOURCE_PARENT_SPAN_ID_ATTRIBUTE,
        "source_span_id": SOURCE_SPAN_ID_ATTRIBUTE,
        "source_trace_id": SOURCE_TRACE_ID_ATTRIBUTE,
        "span_data": SPAN_DATA_ATTRIBUTE,
        "span_type": SPAN_TYPE_ATTRIBUTE,
        "trace_data": TRACE_DATA_ATTRIBUTE,
        "trace_id": TRACE_ID_ATTRIBUTE,
        "translation_error_message": TRANSLATION_ERROR_MESSAGE_ATTRIBUTE,
        "translation_error_type": TRANSLATION_ERROR_TYPE_ATTRIBUTE,
    }
    assert contract["known_span_types"] == [
        "agent",
        "custom",
        "function",
        "generation",
        "guardrail",
        "handoff",
        "mcp_tools",
        "response",
        "speech",
        "speech_group",
        "task",
        "transcription",
        "turn",
    ]


class ExampleEnum(Enum):
    VALUE = "value"


@dataclass
class ExampleData:
    payload: bytes


def test_json_safe_serialization_handles_structured_and_unusual_application_values() -> None:
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic

    serialized = json_safe(
        {
            "bytes": b"complete",
            "dataclass": ExampleData(payload=b"nested"),
            "enum": ExampleEnum.VALUE,
            "large_integer": 2**63,
            "nan": float("nan"),
            "cycle": cyclic,
        }
    )
    encoded = json.dumps(serialized, allow_nan=False)

    assert "Y29tcGxldGU=" in encoded
    assert "bmVzdGVk" in encoded
    assert '"enum": "value"' in encoded
    assert str(2**63) in encoded
    assert '"__junjo_type": "cycle"' in encoded


def test_source_tracing_credential_is_never_serialized() -> None:
    raw = final_span_attributes(
        source_span(AgentSpanData(name="Coordinator"), tracing_api_key="secret-api-key")
    )[SPAN_DATA_ATTRIBUTE]

    assert "secret-api-key" not in raw
    assert "tracing_api_key\"" not in raw
    assert json.loads(raw)["tracing_api_key_configured"] is True


def test_source_error_sets_truthful_error_type_and_keeps_complete_error() -> None:
    attributes = final_span_attributes(
        source_span(
            FunctionSpanData(name="lookup", input=None, output=None),
            error={"message": "Lookup failed", "data": {"name": "LookupError", "code": "missing"}},
        )
    )
    payload = json.loads(attributes[SPAN_DATA_ATTRIBUTE])

    assert attributes["error.type"] == "LookupError"
    assert payload["error"]["data"] == {"name": "LookupError", "code": "missing"}
