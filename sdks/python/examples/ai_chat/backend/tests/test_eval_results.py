"""Deterministic tests for application-owned live-eval result artifacts."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

import pytest
from junjo.agent import AssistantToolCallsMessage, ToolCall, ToolResultMessage
from pydantic import BaseModel, ValidationError

from ai_chat.config import DebugSettings, ModelProvider, Settings
from ai_chat.evals.agent_evidence import tool_transcript_evidence
from ai_chat.evals.judges import QualityJudgment, judge_text
from ai_chat.evals.provider import judge_images, provider_identity
from ai_chat.evals.results import EvalResult, EvalResultRecorder, studio_execution_url

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class RecordingJudgeLanguage:
    def __init__(self) -> None:
        self.prompt: str | None = None

    async def generate_text(self, *, prompt: str) -> str:
        raise AssertionError(f"Unexpected text request: {prompt}")

    async def generate_structured(
        self,
        *,
        prompt: str,
        output_type: type[StructuredOutput],
    ) -> StructuredOutput:
        self.prompt = prompt
        return output_type.model_validate({"passed": True, "score": 0.8, "reason": "The subject meets the rubric."})


def test_eval_result_is_portable_and_written_atomically(tmp_path: Path) -> None:
    result = EvalResult(
        dataset_id="response/quality",
        dataset_version="v1",
        case_id="general continuity",
        capability="general_response",
        prompt_version="general-v1",
        provider="google",
        model="gemini-test",
        executable_type="workflow",
        run_id="workflow-run",
        passed=True,
        score=0.9,
        reason="Persona and history are coherent.",
        duration_ms=123,
        usage={
            "v": 1,
            "modelResponses": 1,
            "fields": {"inputTokens": {"sum": 24, "observations": 1}},
        },
        studio_url="http://localhost:26153/resolve/executable",
        recorded_at=datetime(2026, 7, 15, tzinfo=UTC),
    )

    path = EvalResultRecorder(tmp_path).record(result)

    assert path.name == "response-quality--general-continuity--workflow-run.json"
    assert EvalResult.model_validate(json.loads(path.read_text())) == result
    assert not list(tmp_path.glob("*.tmp"))
    assert result.usage is not None
    with pytest.raises(TypeError):
        result.usage.fields["outputTokens"] = result.usage.fields["inputTokens"]

    payload = result.model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvalResult.model_validate(payload)


def test_studio_execution_url_uses_runtime_resolution_contract() -> None:
    debug = DebugSettings(enabled=True, studio_ui_url="http://localhost:26153")

    url = studio_execution_url(debug, executable_type="agent", run_id="agent/run")

    assert url == (
        "http://localhost:26153/resolve/executable?"
        "service_namespace=junjo.examples&service_name=ai-chat&"
        "executable_type=agent&runtime_id=agent%2Frun&destination=trace"
    )


def test_studio_execution_url_is_absent_when_debug_is_disabled() -> None:
    assert (
        studio_execution_url(
            DebugSettings(enabled=False, studio_ui_url=None),
            executable_type="workflow",
            run_id="workflow-run",
        )
        is None
    )


async def test_text_judge_uses_closed_schema_and_explicit_rubric() -> None:
    language = RecordingJudgeLanguage()

    judgment = await judge_text(
        language=language,
        rubric="Must mention Junjo.",
        subject="Junjo is present.",
    )

    assert judgment == QualityJudgment(
        passed=True,
        score=0.8,
        reason="The subject meets the rubric.",
    )
    assert language.prompt is not None
    assert "Must mention Junjo." in language.prompt
    assert "Junjo is present." in language.prompt


@pytest.mark.parametrize(
    ("provider", "expected_provider", "expected_text", "expected_multimodal"),
    (
        (ModelProvider.GEMINI, "google", "gemini-text", "gemini-text+gemini-image"),
        (ModelProvider.GROK, "xai", "grok-text", "grok-text+grok-image"),
    ),
)
def test_provider_identity_records_exact_selected_models(
    tmp_path: Path,
    provider: ModelProvider,
    expected_provider: str,
    expected_text: str,
    expected_multimodal: str,
) -> None:
    settings = Settings(
        database_path=tmp_path / "chat.sqlite3",
        image_directory=tmp_path / "images",
        cors_origins=(),
        telemetry=None,
        model_provider=provider,
        gemini_text_model="gemini-text",
        gemini_image_model="gemini-image",
        grok_text_model="grok-text",
        grok_image_model="grok-image",
    )

    assert provider_identity(settings).provider == expected_provider
    assert provider_identity(settings).model == expected_text
    assert provider_identity(settings, include_image_model=True).model == expected_multimodal


async def test_visual_judge_rejects_missing_inputs_before_provider_access(
    tmp_path: Path,
) -> None:
    settings = Settings(
        database_path=tmp_path / "chat.sqlite3",
        image_directory=tmp_path / "images",
        cors_origins=(),
        telemetry=None,
        model_provider=ModelProvider.GEMINI,
    )

    with pytest.raises(ValueError, match="At least one image"):
        await judge_images(
            settings=settings,
            rubric="Visible subject.",
            subject="One portrait.",
            image_paths=[],
        )
    with pytest.raises(FileNotFoundError, match="do not exist"):
        await judge_images(
            settings=settings,
            rubric="Visible subject.",
            subject="One portrait.",
            image_paths=[tmp_path / "missing.png"],
        )


def test_tool_evidence_uses_only_portable_tool_contract_values() -> None:
    transcript = (
        AssistantToolCallsMessage(
            tool_calls=[
                ToolCall(
                    id="call-1",
                    name="search_conversation_history",
                    arguments={"query": "marigold", "limit": 2},
                )
            ]
        ),
        ToolResultMessage(
            tool_call_id="call-1",
            tool_name="search_conversation_history",
            result={"matches": [{"content": "The flower is marigold."}]},
        ),
    )

    evidence = tool_transcript_evidence(transcript)

    assert evidence == [
        {
            "type": "assistant_tool_calls",
            "calls": [
                {
                    "id": "call-1",
                    "name": "search_conversation_history",
                    "arguments": {"query": "marigold", "limit": 2},
                }
            ],
        },
        {
            "type": "tool_result",
            "callId": "call-1",
            "toolName": "search_conversation_history",
            "result": {"matches": [{"content": "The flower is marigold."}]},
        },
    ]
