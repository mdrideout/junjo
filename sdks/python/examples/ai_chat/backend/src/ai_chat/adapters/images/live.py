"""Live provider image renderers with application-owned persistence."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image
from xai_sdk import AsyncClient

from ai_chat.domain.models import ImageArtifact
from ai_chat.domain.ports import IdFactory


class _PngArtifactWriter:
    def __init__(self, *, directory: Path, id_factory: IdFactory) -> None:
        self._directory = directory
        self._id_factory = id_factory
        self._directory.mkdir(parents=True, exist_ok=True)

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


class GeminiImageRenderer:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        directory: Path,
        id_factory: IdFactory,
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._writer = _PngArtifactWriter(
            directory=directory,
            id_factory=id_factory,
        )

    async def render(self, *, prompt: str, alt_text: str) -> ImageArtifact:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
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


class GrokImageRenderer:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        directory: Path,
        id_factory: IdFactory,
    ) -> None:
        self._client = AsyncClient(api_key=api_key)
        self._model = model
        self._writer = _PngArtifactWriter(
            directory=directory,
            id_factory=id_factory,
        )

    async def render(self, *, prompt: str, alt_text: str) -> ImageArtifact:
        result = await self._client.image.sample(
            model=self._model,
            prompt=prompt,
            image_format="base64",
        )
        image_bytes = getattr(result, "image", None)
        if not isinstance(image_bytes, bytes) or not image_bytes:
            raise ValueError("Grok returned no image artifact.")
        return self._writer.write(image_bytes=image_bytes, alt_text=alt_text)
