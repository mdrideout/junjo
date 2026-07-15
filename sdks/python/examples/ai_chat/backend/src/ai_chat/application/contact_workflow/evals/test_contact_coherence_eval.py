"""Credentialed full-Workflow eval for generated contact coherence."""

from pathlib import Path
from time import perf_counter

import pytest
from junjo import ExecutionCorrelation

from ai_chat.application.contact_workflow.factory import create_contact_workflow
from ai_chat.domain.models import ContactSex
from ai_chat.evals.fixtures import require_provider_runtime
from ai_chat.evals.judges import judge_text
from ai_chat.evals.provider import judge_images, live_application, provider_identity
from ai_chat.evals.results import EvalResult, studio_execution_url

pytestmark = pytest.mark.live_eval


async def test_generated_contact_profile_and_avatar_are_coherent(
    tmp_path: Path,
    live_telemetry: object,
) -> None:
    del live_telemetry
    async with live_application(tmp_path) as live:
        runtime = require_provider_runtime(live.application)
        workflow = create_contact_workflow(
            contact_id="eval-generated-contact",
            conversation_id="eval-generated-conversation",
            sex=ContactSex.FEMALE,
            contacts=live.application.store,
            language=runtime.language,
            images=runtime.images,
        )
        started = perf_counter()
        execution = await workflow.execute(
            correlation=ExecutionCorrelation(
                type="ai_chat.eval_case",
                id="generated-contact-coherence",
            )
        )
        duration_ms = round((perf_counter() - started) * 1_000)
        overview = execution.state.result
        assert overview is not None
        contact = overview.contact
        avatar_path = live.settings.image_directory / f"{contact.avatar.id}.png"
        assert avatar_path.is_file()

        profile_judgment = await judge_text(
            language=runtime.language,
            rubric=(
                "Pass only when the name, age, sex, location, biography, job, interests, "
                "family details, and personality form one plausible specific person. The "
                "biography must not contradict the structured profile, expose trait scores, "
                "use markdown, or contain model meta-commentary."
            ),
            subject=contact.model_dump_json(indent=2),
        )
        avatar_judgment = await judge_images(
            settings=live.settings,
            rubric=(
                "Pass only when this is a realistic square dating-profile portrait of the "
                "profiled person's stated age and sex. It must be visually plausible, free "
                "of text and watermarks, and suitable as the same persona described by the "
                "profile. Reject obvious illustration, severe artifacts, or age mismatch."
            ),
            subject=contact.model_dump_json(indent=2),
            image_paths=[avatar_path],
        )
        passed = profile_judgment.passed and avatar_judgment.passed
        identity = provider_identity(live.settings, include_image_model=True)
        artifact = live.recorder.record(
            EvalResult(
                dataset_id="contact-creation-coherence",
                dataset_version="1",
                case_id="generated-female-contact",
                capability="contact.profile_avatar_coherence",
                prompt_version="contact-workflow-v1",
                provider=identity.provider,
                model=identity.model,
                executable_type="workflow",
                run_id=execution.run_id,
                passed=passed,
                score=min(profile_judgment.score, avatar_judgment.score),
                reason=(f"Profile: {profile_judgment.reason} Avatar: {avatar_judgment.reason}"),
                duration_ms=duration_ms,
                studio_url=studio_execution_url(
                    live.settings.debug,
                    executable_type="workflow",
                    run_id=execution.run_id,
                ),
            )
        )
        print(artifact)
        assert passed, f"run_id={execution.run_id}: {profile_judgment}; {avatar_judgment}"
