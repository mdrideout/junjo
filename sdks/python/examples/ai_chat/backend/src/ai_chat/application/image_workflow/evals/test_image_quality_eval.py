"""Credentialed full-Workflow eval for relevant, identity-consistent images."""

from pathlib import Path
from time import perf_counter

import pytest
from junjo import ExecutionCorrelation

from ai_chat.application.image_workflow import create_image_workflow
from ai_chat.domain.models import CreateImageInput
from ai_chat.evals.fixtures import create_fixed_contact, require_provider_runtime
from ai_chat.evals.provider import judge_images, live_application, provider_identity
from ai_chat.evals.results import EvalResult, studio_execution_url

pytestmark = pytest.mark.live_eval


async def test_image_response_is_relevant_and_preserves_visual_identity(
    tmp_path: Path,
    live_telemetry: object,
) -> None:
    del live_telemetry
    async with live_application(tmp_path) as live:
        overview = await create_fixed_contact(
            live.application,
            with_local_avatar=True,
        )
        runtime = require_provider_runtime(live.application)
        request = CreateImageInput(
            prompt=(
                "Send me a casual outdoor selfie from your walk in Prospect Park today. "
                "Wear the denim jacket from your profile photo."
            )
        )
        workflow = create_image_workflow(
            request,
            contact=overview.contact,
            recent_turns=(),
            language=runtime.language,
            images=runtime.images,
        )
        started = perf_counter()
        execution = await workflow.execute(
            correlation=ExecutionCorrelation(
                type="ai_chat.eval_case",
                id="image-relevance-visual-continuity",
            )
        )
        duration_ms = round((perf_counter() - started) * 1_000)
        output = execution.state.output
        assert output is not None
        assert output.image is not None
        source_path = live.settings.image_directory / f"{overview.contact.avatar.id}.png"
        result_path = live.settings.image_directory / f"{output.image.id}.png"
        assert source_path.is_file()
        assert result_path.is_file()

        judgment = await judge_images(
            settings=live.settings,
            rubric=(
                "The first image is Maya's reference portrait and the second is the requested "
                "new photo. Pass only when the second visibly preserves the same adult identity, "
                "looks like a realistic casual outdoor selfie in a park, includes a denim jacket, "
                "and has no text or watermark. Reject identity drift, age drift, illustration, "
                "severe artifacts, or a result unrelated to the request."
            ),
            subject=(
                f"REQUEST:\n{request.prompt}\n\n"
                f"PROFILE:\n{overview.contact.model_dump_json(indent=2)}\n\n"
                f"ACCOMPANYING MESSAGE:\n{output.message}"
            ),
            image_paths=[source_path, result_path],
        )
        identity = provider_identity(live.settings, include_image_model=True)
        artifact = live.recorder.record(
            EvalResult(
                dataset_id="image-response-quality",
                dataset_version="1",
                case_id="prospect-park-selfie",
                capability="image.relevance_visual_continuity",
                prompt_version="image-workflow-v1",
                provider=identity.provider,
                model=identity.model,
                executable_type="workflow",
                run_id=execution.run_id,
                passed=judgment.passed,
                score=judgment.score,
                reason=judgment.reason,
                duration_ms=duration_ms,
                studio_url=studio_execution_url(
                    live.settings.debug,
                    executable_type="workflow",
                    run_id=execution.run_id,
                ),
            )
        )
        print(artifact)
        assert judgment.passed, f"run_id={execution.run_id}: {judgment.reason}"
