"""Credentialed full-Workflow evals for persona-aware text responses."""

from pathlib import Path
from time import perf_counter

import pytest

from ai_chat.domain.models import TurnStatus
from ai_chat.evals.fixtures import (
    create_fixed_contact,
    require_provider_runtime,
    seed_completed_turn,
)
from ai_chat.evals.judges import judge_text
from ai_chat.evals.provider import live_application, provider_identity
from ai_chat.evals.results import EvalResult, studio_execution_url

pytestmark = pytest.mark.live_eval

_RESPONSE_CASES = (
    (
        "general-history-continuity",
        "Wait, what class did I say I signed up for, and which night is it?",
        "turn.general_persona_history",
        "general-response-v1",
        (
            "Pass only when Maya answers in a natural dating-chat voice, correctly remembers "
            "that the user signed up for pottery on Thursday, and does not claim those facts "
            "as her own. The answer must remain consistent with Maya's supplied profile."
        ),
    ),
    (
        "work-specificity",
        "What is the hardest part of your landscape architecture work lately?",
        "turn.work_quality",
        "work-response-v1",
        (
            "Pass only when Maya answers as a landscape architect at Greenline Studio with "
            "specific plausible work detail. Reject generic career advice, contradictions with "
            "her profile or prior exchange, markdown, and model meta-commentary."
        ),
    ),
    (
        "date-local-relevance",
        "Pick one specific place near Brooklyn for our first date and tell me why it fits you.",
        "turn.date_quality",
        "date-response-v1",
        (
            "Pass only when Maya proposes at least one specific, plausible place in or near "
            "Brooklyn and explains why it suits her established interests. Reject invented-sounding "
            "vagueness, geographic mismatch, profile contradictions, and generic lists."
        ),
    ),
)


async def test_persona_history_work_and_date_response_quality(
    tmp_path: Path,
    live_telemetry: object,
) -> None:
    del live_telemetry
    failures: list[str] = []
    async with live_application(tmp_path) as live:
        overview = await create_fixed_contact(
            live.application,
            with_local_avatar=False,
        )
        await seed_completed_turn(
            live.application,
            conversation_id=overview.conversation.id,
            user_message="I signed up for a pottery class on Thursday, and I am a little nervous.",
            assistant_message="That sounds brave—Thursday pottery could end up being a lot of fun.",
        )
        runtime = require_provider_runtime(live.application)
        identity = provider_identity(live.settings)

        for case_id, message, capability, prompt_version, rubric in _RESPONSE_CASES:
            started = perf_counter()
            turn = await live.application.turns.submit(
                conversation_id=overview.conversation.id,
                text=message,
            )
            duration_ms = round((perf_counter() - started) * 1_000)
            assert turn.status is TurnStatus.COMPLETED
            assert turn.assistant_message is not None
            run_id = turn.execution_references.workflow_run_id
            assert run_id is not None
            judgment = await judge_text(
                language=runtime.language,
                rubric=rubric,
                subject=(
                    f"PROFILE:\n{overview.contact.model_dump_json(indent=2)}\n\n"
                    f"CURRENT USER MESSAGE:\n{message}\n\n"
                    f"ASSISTANT RESPONSE:\n{turn.assistant_message.content}\n\n"
                    "GENERAL AGENT RUN ID (present only for the general procedure):\n"
                    f"{turn.execution_references.agent_run_id}"
                ),
            )
            artifact = live.recorder.record(
                EvalResult(
                    dataset_id="turn-response-quality",
                    dataset_version="1",
                    case_id=case_id,
                    capability=capability,
                    prompt_version=prompt_version,
                    provider=identity.provider,
                    model=identity.model,
                    executable_type="workflow",
                    run_id=run_id,
                    passed=judgment.passed,
                    score=judgment.score,
                    reason=judgment.reason,
                    duration_ms=duration_ms,
                    studio_url=studio_execution_url(
                        live.settings.debug,
                        executable_type="workflow",
                        run_id=run_id,
                    ),
                )
            )
            print(artifact)
            if not judgment.passed:
                failures.append(f"{case_id} ({run_id}): {judgment.reason}")

    assert not failures, "\n".join(failures)
