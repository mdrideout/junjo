"""Credentialed Agent evals for deliberate Tool choice and composition."""

import json
from pathlib import Path
from time import perf_counter

import pytest

from ai_chat.application.dependencies import ChatDependencies
from ai_chat.domain.models import ChatAgentInput
from ai_chat.evals.agent_evidence import tool_transcript_evidence
from ai_chat.evals.fixtures import (
    create_fixed_contact,
    require_provider_runtime,
    seed_completed_turn,
)
from ai_chat.evals.judges import judge_text
from ai_chat.evals.provider import live_application, provider_identity
from ai_chat.evals.results import EvalResult, EvalUsage, studio_execution_url

pytestmark = pytest.mark.live_eval

_TOOL_POLICY_CASES = (
    (
        "ordinary-no-tool",
        "How is your evening going?",
        (
            "Pass only when the Agent gives a natural in-character reply without calling either "
            "Tool. This message needs neither older history nor an image. Any Tool call fails."
        ),
    ),
    (
        "older-history-search",
        "What was the secret flower I told you about earlier? Check our older chat if you need to.",
        (
            "Pass only when the Agent calls search_conversation_history, does not call create_image, "
            "uses the returned history, and answers that the secret flower was marigold."
        ),
    ),
    (
        "image-workflow-composition",
        "Send me a new casual selfie from your walk in Prospect Park.",
        (
            "Pass only when the Agent calls create_image, does not merely pretend to create an "
            "image in prose, receives a real image artifact from the Tool's nested Workflow, and "
            "returns that artifact in its final typed output. A history search is unnecessary."
        ),
    ),
)


async def test_agent_tool_choice_composition_and_avoidance(
    tmp_path: Path,
    live_telemetry: object,
) -> None:
    del live_telemetry
    failures: list[str] = []
    async with live_application(tmp_path) as live:
        overview = await create_fixed_contact(
            live.application,
            with_local_avatar=True,
        )
        await seed_completed_turn(
            live.application,
            conversation_id=overview.conversation.id,
            user_message="My secret flower is marigold. Please remember that.",
            assistant_message="Marigold—got it. I will remember.",
        )
        runtime = require_provider_runtime(live.application)
        identity = provider_identity(live.settings, include_image_model=True)

        for index, (case_id, message, rubric) in enumerate(_TOOL_POLICY_CASES, start=1):
            turn_id = f"eval-agent-turn-{index}"
            dependencies = ChatDependencies(
                conversation_id=overview.conversation.id,
                turn_id=turn_id,
                before_sequence=100,
                contact=overview.contact,
                recent_turns=(),
                history=live.application.store,
                language=runtime.language,
                images=runtime.images,
            )
            started = perf_counter()
            result = await live.application.turns.agent.execute(
                ChatAgentInput(
                    conversation_id=overview.conversation.id,
                    turn_id=turn_id,
                    contact=overview.contact,
                    message=message,
                ),
                dependencies=dependencies,
            )
            duration_ms = round((perf_counter() - started) * 1_000)
            transcript = tool_transcript_evidence(result.transcript)
            judgment = await judge_text(
                language=runtime.language,
                rubric=rubric,
                subject=(
                    f"PROFILE:\n{overview.contact.model_dump_json(indent=2)}\n\n"
                    f"CURRENT USER MESSAGE:\n{message}\n\n"
                    "NORMALIZED AGENT TRANSCRIPT:\n"
                    f"{json.dumps(transcript, indent=2, sort_keys=True)}\n\n"
                    f"FINAL TYPED OUTPUT:\n{result.output.model_dump_json(indent=2)}\n\n"
                    "COUNTERS:\n"
                    f"requested={result.tool_call_requested_count}, "
                    f"admitted={result.tool_call_admitted_count}, "
                    f"started={result.tool_call_started_count}, "
                    f"completed={result.tool_call_completed_count}"
                ),
            )
            artifact = live.recorder.record(
                EvalResult(
                    dataset_id="agent-tool-policy",
                    dataset_version="1",
                    case_id=case_id,
                    capability="agent.tool_choice_composition",
                    prompt_version="chat-agent-v1",
                    provider=identity.provider,
                    model=identity.model,
                    executable_type="agent",
                    run_id=result.run_id,
                    passed=judgment.passed,
                    score=judgment.score,
                    reason=judgment.reason,
                    duration_ms=duration_ms,
                    usage=EvalUsage.model_validate(result.usage.to_json()),
                    studio_url=studio_execution_url(
                        live.settings.debug,
                        executable_type="agent",
                        run_id=result.run_id,
                    ),
                )
            )
            print(artifact)
            if not judgment.passed:
                failures.append(f"{case_id} ({result.run_id}): {judgment.reason}")

    assert not failures, "\n".join(failures)
