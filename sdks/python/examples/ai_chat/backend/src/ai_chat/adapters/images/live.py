"""Live image capabilities with application-owned artifact persistence.

Google calls use the installed Google GenAI instrumentation. The xAI SDK's
``image.sample`` operation emits its own OpenTelemetry CLIENT span.
"""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from google.genai import types
from google.genai.client import AsyncClient as GeminiAsyncClient
from PIL import Image
from xai_sdk import AsyncClient

from ai_chat.adapters.provider_call import await_provider_call
from ai_chat.domain.models import ImageArtifact, ImageEditResult
from ai_chat.domain.ports import IdFactory


class _PngArtifactWriter:
    def __init__(self, *, directory: Path, id_factory: IdFactory) -> None:
        self._directory = directory
        self._id_factory = id_factory

    def write(self, *, image_bytes: bytes, alt_text: str) -> ImageArtifact:
        artifact_id = self._id_factory()
        with Image.open(BytesIO(image_bytes)) as source:
            source.convert("RGB").save(
                self._directory / f"{artifact_id}.png",
                format="PNG",
            )
        return ImageArtifact(
            id=artifact_id,
            url=f"/api/images/{artifact_id}.png",
            alt_text=alt_text,
        )

    def open(self, artifact: ImageArtifact) -> Image.Image:
        path = self._directory / f"{artifact.id}.png"
        if not path.is_file():
            raise FileNotFoundError(f"Image artifact {artifact.id} is not available locally.")
        with Image.open(path) as source:
            return source.copy()


class GeminiImageModel:
    def __init__(
        self,
        *,
        client: GeminiAsyncClient,
        model: str,
        timeout_seconds: float,
        directory: Path,
        id_factory: IdFactory,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._writer = _PngArtifactWriter(
            directory=directory,
            id_factory=id_factory,
        )

    async def generate(self, *, prompt: str, alt_text: str) -> ImageArtifact:
        response = await await_provider_call(
            self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
            ),
            timeout_seconds=self._timeout_seconds,
        )
        for candidate in response.candidates or []:
            if candidate.content is None:
                continue
            for part in candidate.content.parts or []:
                if part.inline_data is not None and part.inline_data.data:
                    return self._writer.write(
                        image_bytes=part.inline_data.data,
                        alt_text=alt_text,
                    )
        raise ValueError("Gemini returned no image artifact.")

    async def edit(
        self,
        *,
        source: ImageArtifact,
        prompt: str,
        alt_text: str,
    ) -> ImageEditResult:
        response = await await_provider_call(
            self._client.models.generate_content(
                model=self._model,
                contents=[prompt, self._writer.open(source)],
                config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
            ),
            timeout_seconds=self._timeout_seconds,
        )
        image_bytes: bytes | None = None
        text_parts: list[str] = []
        for candidate in response.candidates or []:
            if candidate.content is None:
                continue
            for part in candidate.content.parts or []:
                if part.text:
                    text_parts.append(part.text.strip())
                if part.inline_data is not None and part.inline_data.data:
                    image_bytes = part.inline_data.data
        if image_bytes is None:
            raise ValueError("Gemini returned no edited image artifact.")
        return ImageEditResult(
            artifact=self._writer.write(image_bytes=image_bytes, alt_text=alt_text),
            text="\n".join(part for part in text_parts if part) or None,
        )


class GrokImageModel:
    def __init__(
        self,
        *,
        client: AsyncClient,
        model: str,
        timeout_seconds: float,
        directory: Path,
        id_factory: IdFactory,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._writer = _PngArtifactWriter(
            directory=directory,
            id_factory=id_factory,
        )

    async def generate(self, *, prompt: str, alt_text: str) -> ImageArtifact:
        image_bytes = await await_provider_call(
            self._sample_image(prompt=prompt),
            timeout_seconds=self._timeout_seconds,
        )
        if not image_bytes:
            raise ValueError("Grok returned no image artifact.")
        return self._writer.write(image_bytes=image_bytes, alt_text=alt_text)

    async def edit(
        self,
        *,
        source: ImageArtifact,
        prompt: str,
        alt_text: str,
    ) -> ImageEditResult:
        image = self._writer.open(source)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        image_url = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"
        image_bytes = await await_provider_call(
            self._sample_image(prompt=prompt, image_url=image_url),
            timeout_seconds=self._timeout_seconds,
        )
        if not image_bytes:
            raise ValueError("Grok returned no edited image artifact.")
        return ImageEditResult(
            artifact=self._writer.write(image_bytes=image_bytes, alt_text=alt_text),
        )

    async def _sample_image(
        self,
        *,
        prompt: str,
        image_url: str | None = None,
    ) -> bytes:
        result = await self._client.image.sample(
            model=self._model,
            image_url=image_url,
            prompt=prompt,
            image_format="base64",
            aspect_ratio="1:1",
        )
        return await result.image
