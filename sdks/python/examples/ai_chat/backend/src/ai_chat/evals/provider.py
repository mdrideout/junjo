"""Explicit live provider and application composition for AI Chat evals."""

import base64
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image
from xai_sdk import AsyncClient
from xai_sdk.chat import image as xai_image
from xai_sdk.chat import system, user

from ai_chat.adapters.model import GeminiLanguageModel, GrokLanguageModel
from ai_chat.adapters.model.gemini import gemini_response_schema
from ai_chat.adapters.provider_call import await_provider_call
from ai_chat.bootstrap import ChatApplication, build_application
from ai_chat.config import ModelProvider, Settings
from ai_chat.domain.ports import LanguageModel
from ai_chat.evals.judges import QualityJudgment
from ai_chat.evals.results import EvalResultRecorder


@dataclass(frozen=True, slots=True)
class LiveEvalApplication:
    """An isolated real application plus persistent evaluation evidence."""

    settings: Settings
    application: ChatApplication
    recorder: EvalResultRecorder


@dataclass(frozen=True, slots=True)
class ProviderIdentity:
    """Stable provider and model labels recorded with evaluation evidence."""

    provider: str
    model: str


def provider_identity(
    settings: Settings,
    *,
    include_image_model: bool = False,
) -> ProviderIdentity:
    """Return the selected provider and exact model identity."""

    if settings.model_provider is ModelProvider.GEMINI:
        provider = "google"
        text_model = settings.gemini_text_model
        image_model = settings.gemini_image_model
    else:
        provider = "xai"
        text_model = settings.grok_text_model
        image_model = settings.grok_image_model
    model = f"{text_model}+{image_model}" if include_image_model else text_model
    return ProviderIdentity(provider=provider, model=model)


@asynccontextmanager
async def live_application(working_directory: Path) -> AsyncIterator[LiveEvalApplication]:
    """Run one isolated real application while preserving evidence artifacts."""

    environment_settings = Settings.from_environment()
    settings = replace(
        environment_settings,
        database_path=working_directory / "chat.sqlite3",
        image_directory=working_directory / "images",
    )
    application = build_application(settings)
    await application.initialize()
    try:
        yield LiveEvalApplication(
            settings=settings,
            application=application,
            recorder=EvalResultRecorder(environment_settings.database_path.parent / "eval-results"),
        )
    finally:
        await application.close()


@asynccontextmanager
async def live_language_model() -> AsyncIterator[tuple[Settings, LanguageModel]]:
    settings = Settings.from_environment()
    if settings.model_provider is ModelProvider.GEMINI:
        assert settings.gemini_api_key is not None
        client = genai.Client(api_key=settings.gemini_api_key).aio
        try:
            yield (
                settings,
                GeminiLanguageModel(
                    client=client,
                    model=settings.gemini_text_model,
                    timeout_seconds=settings.provider_timeout_seconds,
                ),
            )
        finally:
            await client.aclose()
    else:
        assert settings.xai_api_key is not None
        client = AsyncClient(
            api_key=settings.xai_api_key,
            timeout=settings.provider_timeout_seconds,
        )
        try:
            yield (
                settings,
                GrokLanguageModel(
                    client=client,
                    model=settings.grok_text_model,
                    timeout_seconds=settings.provider_timeout_seconds,
                ),
            )
        finally:
            await client.close()


async def judge_images(
    *,
    settings: Settings,
    rubric: str,
    subject: str,
    image_paths: Sequence[Path],
) -> QualityJudgment:
    """Judge local images with the selected provider's multimodal text model."""

    if not image_paths:
        raise ValueError("At least one image is required for a visual judgment.")
    missing = [path for path in image_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Evaluation images do not exist: {missing}")
    prompt = _judge_prompt(rubric=rubric, subject=subject)
    if settings.model_provider is ModelProvider.GEMINI:
        return await _judge_images_with_gemini(
            settings=settings,
            prompt=prompt,
            image_paths=image_paths,
        )
    return await _judge_images_with_grok(
        settings=settings,
        prompt=prompt,
        image_paths=image_paths,
    )


async def _judge_images_with_gemini(
    *,
    settings: Settings,
    prompt: str,
    image_paths: Sequence[Path],
) -> QualityJudgment:
    assert settings.gemini_api_key is not None
    client = genai.Client(api_key=settings.gemini_api_key).aio
    images: list[Image.Image] = []
    try:
        for path in image_paths:
            with Image.open(path) as source:
                images.append(source.copy())
        response = await await_provider_call(
            client.models.generate_content(
                model=settings.gemini_text_model,
                contents=[prompt, *images],
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=gemini_response_schema(QualityJudgment),
                ),
            ),
            timeout_seconds=settings.provider_timeout_seconds,
        )
        if response.parsed is not None:
            return QualityJudgment.model_validate(response.parsed)
        if response.text:
            return QualityJudgment.model_validate_json(response.text)
        raise ValueError("Gemini returned no visual judgment.")
    finally:
        for image in images:
            image.close()
        await client.aclose()


async def _judge_images_with_grok(
    *,
    settings: Settings,
    prompt: str,
    image_paths: Sequence[Path],
) -> QualityJudgment:
    assert settings.xai_api_key is not None
    client = AsyncClient(
        api_key=settings.xai_api_key,
        timeout=settings.provider_timeout_seconds,
    )
    try:
        visual_content = [
            xai_image(
                "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii"),
                detail="high",
            )
            for path in image_paths
        ]
        chat = client.chat.create(
            model=settings.grok_text_model,
            messages=[
                system("Return only the requested strict structured judgment."),
                user(prompt, *visual_content),
            ],
            store_messages=False,
        )
        _, parsed = await await_provider_call(
            chat.parse(QualityJudgment),
            timeout_seconds=settings.provider_timeout_seconds,
        )
        return QualityJudgment.model_validate(parsed)
    finally:
        await client.close()


def _judge_prompt(*, rubric: str, subject: str) -> str:
    return f"""
Evaluate the supplied image or ordered images against the rubric. When two
images are supplied, the first is the identity reference and the second is the
candidate. Be strict and judge only visible evidence. Return passed, a score
from 0 to 1, and a concise reason.

RUBRIC:
{rubric}

SUBJECT:
{subject}
""".strip()
