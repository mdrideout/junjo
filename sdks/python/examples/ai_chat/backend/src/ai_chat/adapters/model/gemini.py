"""Google Gemini ModelDriver adapter."""

from google import genai
from google.genai import types
from junjo import ModelDriverBinding, ModelDriverDescriptor
from junjo.agent import ModelRequest

from .provider_decision import ProviderDecision, provider_prompt


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
