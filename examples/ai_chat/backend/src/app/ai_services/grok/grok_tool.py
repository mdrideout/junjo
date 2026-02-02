import base64
import inspect
import os
from io import BytesIO
from typing import Any, TypeVar

from loguru import logger
from PIL import Image
from pydantic import BaseModel
from xai_sdk import AsyncClient
from xai_sdk.chat import assistant, image as xai_image, system, user

T = TypeVar("T", bound=BaseModel)


class GrokAPIError(RuntimeError):
    pass


class GrokTool:
    """
    A tool for making requests to xAI Grok via the official xAI Python SDK (`xai-sdk`).

    Notes:
    - This tool is intentionally stateless: callers provide the full message history each call.
    - Server-side conversation storage is disabled (`store_messages=False`).
    """

    _prompt: str | None
    _model: str
    _client: AsyncClient

    def __init__(
        self,
        *,
        prompt: str | None = None,
        model: str,
        timeout_s: float = 60.0,
        api_key: str | None = None,
    ) -> None:
        xai_api_key = api_key or os.getenv("XAI_API_KEY")
        if not xai_api_key:
            raise ValueError("XAI_API_KEY environment variable not set")

        # The xAI SDK uses seconds for timeouts (default: 900s).
        timeout = max(1, int(timeout_s))

        self._client = AsyncClient(api_key=xai_api_key, timeout=timeout)
        self._prompt = prompt
        self._model = model

    @staticmethod
    async def _maybe_await(value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    @staticmethod
    def build_messages_from_prompt(prompt: str) -> list[dict[str, Any]]:
        """
        Convenience helper to build a minimal message list from a single prompt.
        """

        return [{"role": "user", "content": prompt}]

    @staticmethod
    def build_image_input_message(*, image_url: str, text: str, mime_type: str | None = None) -> dict[str, Any]:
        """
        Convenience helper for vision-style chat messages (image understanding).

        If `mime_type` is provided, `image_url` is assumed to be raw base64 (no prefix) and will be converted to a
        `data:<mime>;base64,...` data URL.
        """

        url = image_url
        if mime_type is not None and not image_url.startswith("data:"):
            url = f"data:{mime_type};base64,{image_url}"

        return {
            "role": "user",
            "content": [
                {"type": "input_image", "image_url": url},
                {"type": "input_text", "text": text},
            ],
        }

    @staticmethod
    def _stringify(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)

    @classmethod
    def _to_xai_message(cls, message: dict[str, Any]) -> Any:
        role = cls._stringify(message.get("role")).strip().lower()
        content = message.get("content")

        if role == "system":
            return system(cls._stringify(content))

        if role == "assistant":
            return assistant(cls._stringify(content))

        if role != "user":
            logger.warning(f"Unknown message role '{role}', treating as user.")

        # user messages can interleave text + images: user("...", image("..."), image("..."))
        if isinstance(content, str):
            return user(content)

        if isinstance(content, list):
            text_parts: list[str] = []
            image_parts: list[Any] = []

            for part in content:
                if not isinstance(part, dict):
                    continue

                part_type = part.get("type")
                if part_type in ("input_text", "text"):
                    text = part.get("text")
                    if isinstance(text, str) and text:
                        text_parts.append(text)
                    continue

                if part_type in ("input_image", "image"):
                    image_url = part.get("image_url")
                    if isinstance(image_url, str) and image_url:
                        image_parts.append(xai_image(image_url=image_url))
                    continue

            text = "\n".join(text_parts).strip()
            if image_parts:
                return user(text, *image_parts)

            return user(text)

        return user(cls._stringify(content))

    def _xai_messages(self, messages: list[dict[str, Any]] | None) -> list[Any]:
        if messages is None:
            if not self._prompt:
                raise ValueError("Either `messages` must be provided or `prompt` must be set in GrokTool().")
            messages = self.build_messages_from_prompt(self._prompt)

        if not isinstance(messages, list) or not messages:
            raise ValueError("messages must be a non-empty list")

        return [self._to_xai_message(m) for m in messages]

    async def text_request(self, *, messages: list[dict[str, Any]] | None = None) -> str:
        """
        Create a text response using xAI's chat API.

        Server-side message storage is disabled (`store_messages=False`).
        """

        xai_messages = self._xai_messages(messages)

        try:
            chat = self._client.chat.create(model=self._model, messages=xai_messages, store_messages=False)
            response = await self._maybe_await(chat.sample())
        except Exception as e:
            logger.exception("xAI chat request failed")
            raise GrokAPIError(str(e)) from e

        text = getattr(response, "content", None)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("No text in xAI response")

        return text.strip()

    async def schema_request(self, schema: type[T], *, messages: list[dict[str, Any]] | None = None) -> T:
        """
        Request structured output and validate it against a Pydantic schema.
        """

        xai_messages = self._xai_messages(messages)

        try:
            chat = self._client.chat.create(model=self._model, messages=xai_messages, store_messages=False)
            parse_result = chat.parse(schema)
            response, parsed = await self._maybe_await(parse_result)
        except Exception as e:
            logger.exception("xAI schema request failed")
            raise GrokAPIError(str(e)) from e

        _ = response  # reserved for future logging/telemetry
        if parsed is None:
            raise ValueError("Parsed schema result is None")

        return parsed

    @staticmethod
    def _data_url(image_bytes: bytes, *, mime_type: str) -> str:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{mime_type};base64,{b64}"

    @staticmethod
    def _ensure_png_bytes(image_bytes: bytes) -> bytes:
        """
        Our app persists generated images as `.png`. Convert bytes to PNG when possible.
        """

        try:
            with Image.open(BytesIO(image_bytes)) as img:
                out = BytesIO()
                img.save(out, format="PNG")
                return out.getvalue()
        except Exception:
            return image_bytes

    async def image_request(
        self,
        *,
        prompt: str | None = None,
        n: int = 1,
        aspect_ratio: str | None = None,
    ) -> bytes:
        """
        Generate an image and return the first image bytes.

        Uses `image_format="base64"` to avoid xAI-hosted image URLs.
        """

        image_prompt = prompt or self._prompt
        if not image_prompt:
            raise ValueError("Either `prompt` must be provided or `prompt` must be set in GrokTool().")

        try:
            if n != 1 or aspect_ratio is not None:
                results = await self._maybe_await(
                    self._client.image.sample_batch(
                        model=self._model,
                        prompt=image_prompt,
                        n=n,
                        image_format="base64",
                        aspect_ratio=aspect_ratio,
                    )
                )
                result = results[0]
            else:
                result = await self._maybe_await(
                    self._client.image.sample(
                        model=self._model,
                        prompt=image_prompt,
                        image_format="base64",
                    )
                )
        except Exception as e:
            logger.exception("xAI image generation request failed")
            raise GrokAPIError(str(e)) from e

        image_bytes = await self._maybe_await(getattr(result, "image", None))
        if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes:
            raise ValueError("No image bytes in xAI image response")

        return self._ensure_png_bytes(bytes(image_bytes))

    async def image_edit_request(
        self,
        image_bytes: bytes,
        *,
        image_mime_type: str = "image/png",
        prompt: str | None = None,
    ) -> bytes:
        """
        Edit an image and return the edited image bytes.

        Uses `image_format="base64"` to avoid xAI-hosted image URLs.
        """

        edit_prompt = prompt or self._prompt
        if not edit_prompt:
            raise ValueError("Either `prompt` must be provided or `prompt` must be set in GrokTool().")

        data_url = self._data_url(image_bytes, mime_type=image_mime_type)

        try:
            result = await self._maybe_await(
                self._client.image.sample(
                    model=self._model,
                    image_url=data_url,
                    prompt=edit_prompt,
                    image_format="base64",
                )
            )
        except Exception as e:
            logger.exception("xAI image edit request failed")
            raise GrokAPIError(str(e)) from e

        edited_bytes = await self._maybe_await(getattr(result, "image", None))
        if not isinstance(edited_bytes, (bytes, bytearray)) or not edited_bytes:
            raise ValueError("No image bytes in xAI image edit response")

        return self._ensure_png_bytes(bytes(edited_bytes))
