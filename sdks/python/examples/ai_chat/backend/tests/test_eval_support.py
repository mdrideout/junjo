"""Deterministic tests for application-owned quality-evaluation support."""

from pathlib import Path
from typing import TypeVar

import pytest
from junjo.agent import AssistantToolCallsMessage, ToolCall, ToolResultMessage
from pydantic import BaseModel

from ai_chat.config import ModelProvider, Settings
from ai_chat.evals.agent_evidence import tool_transcript_evidence
from ai_chat.evals.judges import QualityJudgment, judge_text
from ai_chat.evals.provider import judge_images

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
        return output_type.model_validate({"passed": True, "reason": "The subject meets the rubric."})


async def test_text_judge_uses_closed_schema_and_explicit_rubric() -> None:
    language = RecordingJudgeLanguage()

    judgment = await judge_text(
        language=language,
        rubric="Must mention Junjo.",
        subject="Junjo is present.",
    )

    assert judgment == QualityJudgment(
        passed=True,
        reason="The subject meets the rubric.",
    )
    assert language.prompt is not None
    assert "Must mention Junjo." in language.prompt
    assert "Junjo is present." in language.prompt


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
