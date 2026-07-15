"""Provider translation, execution-bound, and ownership contract tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import types
from junjo.agent import FinalOutputResponse, ModelRequest, ToolCallsResponse
from PIL import Image
from xai_sdk.proto import usage_pb2

from ai_chat.adapters.model.gemini import (
    GeminiModelDriver,
    gemini_model_binding,
    gemini_response_schema,
)
from ai_chat.adapters.model.grok import GrokModelDriver, grok_model_binding
from ai_chat.adapters.model.provider_decision import ProviderDecision, ProviderToolCall
from ai_chat.adapters.provider_call import await_provider_call
from ai_chat.config import Settings
from ai_chat.evals.judges import QualityJudgment
from ai_chat.evals.provider import judge_images


def _request() -> ModelRequest:
    return ModelRequest(
        agent_key="ai_chat",
        run_id="agent-run",
        ordinal=1,
        instructions="Respond.",
        messages=(),
        tools=(),
        output_schema={"type": "object"},
    )


class FakeGeminiModels:
    def __init__(self, response: object) -> None:
        self.response = response
        self.request: dict[str, object] | None = None

    async def generate_content(self, **request: object) -> object:
        self.request = request
        return self.response


class FakeGeminiClient:
    def __init__(self, response: object) -> None:
        self.models = FakeGeminiModels(response)

    async def aclose(self) -> None:
        return None


class FakeGrokChat:
    def __init__(self, response: object, decision: ProviderDecision) -> None:
        self.response = response
        self.decision = decision

    async def parse(self, _: type[ProviderDecision]) -> tuple[object, ProviderDecision]:
        return self.response, self.decision


class FakeGrokChats:
    def __init__(self, response: object, decision: ProviderDecision) -> None:
        self.response = response
        self.decision = decision

    def create(self, **_: object) -> FakeGrokChat:
        return FakeGrokChat(self.response, self.decision)


class FakeGrokClient:
    def __init__(self, response: object, decision: ProviderDecision) -> None:
        self.chat = FakeGrokChats(response, decision)


@pytest.mark.asyncio
async def test_gemini_agent_driver_reports_exact_available_usage() -> None:
    decision = ProviderDecision(
        decision="final_output",
        output_json='{"message":"hello"}',
    )
    usage = SimpleNamespace(
        prompt_token_count=13,
        candidates_token_count=5,
        cached_content_token_count=3,
        thoughts_token_count=None,
        total_token_count=18,
    )
    response = SimpleNamespace(parsed=decision, text=None, usage_metadata=usage)
    client = FakeGeminiClient(response)
    driver = GeminiModelDriver(
        client=client,  # type: ignore[arg-type]
        model="gemini-test",
        timeout_seconds=1,
    )

    result = await driver.request(_request())

    assert isinstance(result, FinalOutputResponse)
    assert result.usage is not None
    assert result.usage.to_json() == {
        "v": 1,
        "inputTokens": 13,
        "outputTokens": 5,
        "cachedInputTokens": 3,
        "totalTokens": 18,
    }


@pytest.mark.asyncio
async def test_grok_agent_driver_reports_only_protobuf_fields_present_on_wire() -> None:
    decision = ProviderDecision(
        decision="final_output",
        output_json='{"message":"hello"}',
    )
    usage = usage_pb2.SamplingUsage(
        prompt_tokens=21,
        completion_tokens=8,
        reasoning_tokens=2,
        total_tokens=31,
    )
    response = SimpleNamespace(usage=usage)
    client = FakeGrokClient(response, decision)
    driver = GrokModelDriver(
        client=client,  # type: ignore[arg-type]
        model="grok-test",
        timeout_seconds=1,
    )

    result = await driver.request(_request())

    assert isinstance(result, FinalOutputResponse)
    assert result.usage is not None
    assert result.usage.to_json() == {
        "v": 1,
        "inputTokens": 21,
        "outputTokens": 8,
        "reasoningTokens": 2,
        "totalTokens": 31,
    }


def test_live_agent_bindings_are_shared_application_owned_drivers() -> None:
    decision = ProviderDecision(
        decision="final_output",
        output_json='{"message":"hello"}',
    )
    gemini_client = FakeGeminiClient(SimpleNamespace(parsed=decision, text=None, usage_metadata=None))
    grok_client = FakeGrokClient(
        SimpleNamespace(usage=usage_pb2.SamplingUsage()),
        decision,
    )

    gemini = gemini_model_binding(
        client=gemini_client,  # type: ignore[arg-type]
        model="gemini-test",
        timeout_seconds=7,
    )
    grok = grok_model_binding(
        client=grok_client,  # type: ignore[arg-type]
        model="grok-test",
        timeout_seconds=7,
    )

    for binding in (gemini, grok):
        assert binding.shared_driver is not None
        assert binding.factory is None
        assert binding.descriptor.settings["timeout_seconds"] == 7
        assert binding.descriptor.settings["decision_format"] == "structured-json-envelope-v2"


def test_provider_decision_uses_closed_outer_schema_and_decodes_typed_payloads() -> None:
    schema = ProviderDecision.model_json_schema()
    assert '"additionalProperties": true' not in json.dumps(schema)
    assert "additionalProperties" not in json.dumps(
        gemini_response_schema(ProviderDecision)
    )

    final = ProviderDecision(
        decision="final_output",
        output_json='{"message":"hello","image":null}',
    ).to_junjo()
    assert isinstance(final, FinalOutputResponse)
    assert final.output == {"message": "hello", "image": None}

    tools = ProviderDecision(
        decision="tool_calls",
        tool_calls=[
            ProviderToolCall(
                id="call-1",
                name="search_conversation_history",
                arguments_json='{"query":"pottery","limit":3}',
            )
        ],
    ).to_junjo()
    assert isinstance(tools, ToolCallsResponse)
    assert tools.tool_calls[0].arguments == {"query": "pottery", "limit": 3}


@pytest.mark.asyncio
async def test_gemini_visual_judge_uses_provider_supported_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = SimpleNamespace(
        parsed=QualityJudgment(passed=True, score=1, reason="coherent"),
        text=None,
    )
    client = FakeGeminiClient(response)
    monkeypatch.setattr(
        "ai_chat.evals.provider.genai.Client",
        lambda **_: SimpleNamespace(aio=client),
    )
    image_path = tmp_path / "candidate.png"
    Image.new("RGB", (2, 2)).save(image_path)
    settings = Settings(
        database_path=tmp_path / "chat.sqlite3",
        image_directory=tmp_path,
        cors_origins=(),
        telemetry=None,
        gemini_api_key="synthetic-test-key",
    )

    judgment = await judge_images(
        settings=settings,
        rubric="The image is coherent.",
        subject="Candidate",
        image_paths=[image_path],
    )

    assert judgment.passed
    assert client.models.request is not None
    config = client.models.request["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert "additionalProperties" not in json.dumps(config.response_schema)


@pytest.mark.parametrize(
    "decision",
    [
        ProviderDecision(decision="final_output", output_json="[]"),
        ProviderDecision(
            decision="tool_calls",
            tool_calls=[
                ProviderToolCall(
                    id="call-1",
                    name="search_conversation_history",
                    arguments_json="not-json",
                )
            ],
        ),
    ],
)
def test_provider_decision_rejects_non_object_payloads(decision: ProviderDecision) -> None:
    with pytest.raises(ValueError, match="Provider returned"):
        decision.to_junjo()


@pytest.mark.asyncio
async def test_provider_deadline_cancels_the_operation() -> None:
    cancelled = asyncio.Event()

    async def blocked() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with pytest.raises(TimeoutError):
        await await_provider_call(blocked(), timeout_seconds=0.001)

    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_external_cancellation_remains_cancelled_error() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def blocked() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = asyncio.create_task(
        await_provider_call(blocked(), timeout_seconds=60),
    )
    await started.wait()
    task.cancel("caller_cancelled")

    with pytest.raises(asyncio.CancelledError):
        await task

    assert cancelled.is_set()
