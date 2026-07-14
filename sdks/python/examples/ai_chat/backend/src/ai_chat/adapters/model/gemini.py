"""Google Gemini adapters for bounded Workflow calls and Agent decisions."""

from typing import TypeVar

from google import genai
from google.genai import types
from junjo import ModelDriverBinding, ModelDriverDescriptor
from junjo.agent import ModelRequest
from pydantic import BaseModel

from .provider_decision import ProviderDecision, provider_prompt

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class GeminiLanguageModel:
    """Narrow application text capability; Agent operation translation is separate."""

    def __init__(self, *, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def generate_text(self, *, prompt: str) -> str:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
        )
        text = (response.text or "").strip()
        if not text:
            raise ValueError("Gemini returned no text.")
        return text

    async def generate_structured(
        self,
        *,
        prompt: str,
        output_type: type[StructuredOutput],
    ) -> StructuredOutput:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=output_type,
            ),
        )
        if response.parsed is not None:
            return output_type.model_validate(response.parsed)
        if response.text:
            return output_type.model_validate_json(response.text)
        raise ValueError("Gemini returned no structured response.")


class GeminiModelDriver:
    def __init__(self, *, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def request(self, request: ModelRequest) -> object:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=provider_prompt(request),
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=ProviderDecision,
            ),
        )
        if response.parsed is not None:
            decision = ProviderDecision.model_validate(response.parsed)
        elif response.text:
            decision = ProviderDecision.model_validate_json(response.text)
        else:
            raise ValueError("Gemini returned no structured Agent decision.")
        return decision.to_junjo()


def gemini_model_binding(*, api_key: str, model: str) -> ModelDriverBinding:
    return ModelDriverBinding.shared(
        descriptor=ModelDriverDescriptor(
            driver_key="ai_chat_gemini",
            provider="google",
            model=model,
            settings={"decision_format": "structured-json-v1"},
        ),
        driver=GeminiModelDriver(api_key=api_key, model=model),
    )
