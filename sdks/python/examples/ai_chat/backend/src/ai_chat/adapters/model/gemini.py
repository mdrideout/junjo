"""Google Gemini adapters for bounded Workflow calls and Agent decisions."""

from typing import Any, TypeVar, cast

from google.genai import types
from google.genai.client import AsyncClient as GeminiAsyncClient
from junjo import ModelDriverBinding, ModelDriverDescriptor
from junjo.agent import ModelRequest, ModelUsage
from pydantic import BaseModel

from ai_chat.adapters.provider_call import await_provider_call

from .provider_decision import ProviderDecision, provider_prompt

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class GeminiLanguageModel:
    """Narrow application text capability; Agent operation translation is separate."""

    def __init__(
        self,
        *,
        client: GeminiAsyncClient,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def generate_text(self, *, prompt: str) -> str:
        response = await await_provider_call(
            self._client.models.generate_content(
                model=self._model,
                contents=prompt,
            ),
            timeout_seconds=self._timeout_seconds,
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
        response = await await_provider_call(
            self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=gemini_response_schema(output_type),
                ),
            ),
            timeout_seconds=self._timeout_seconds,
        )
        if response.parsed is not None:
            return output_type.model_validate(response.parsed)
        if response.text:
            return output_type.model_validate_json(response.text)
        raise ValueError("Gemini returned no structured response.")


class GeminiModelDriver:
    def __init__(
        self,
        *,
        client: GeminiAsyncClient,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def request(self, request: ModelRequest) -> object:
        response = await await_provider_call(
            self._client.models.generate_content(
                model=self._model,
                contents=provider_prompt(request),
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=gemini_response_schema(ProviderDecision),
                ),
            ),
            timeout_seconds=self._timeout_seconds,
        )
        if response.parsed is not None:
            decision = ProviderDecision.model_validate(response.parsed)
        elif response.text:
            decision = ProviderDecision.model_validate_json(response.text)
        else:
            raise ValueError("Gemini returned no structured Agent decision.")
        return decision.to_junjo(usage=_gemini_usage(response))


def gemini_model_binding(
    *,
    client: GeminiAsyncClient,
    model: str,
    timeout_seconds: float,
) -> ModelDriverBinding:
    return ModelDriverBinding.shared(
        descriptor=ModelDriverDescriptor(
            driver_key="ai_chat_gemini",
            provider="google",
            model=model,
            settings={
                "decision_format": "structured-json-envelope-v2",
                "timeout_seconds": timeout_seconds,
            },
        ),
        driver=GeminiModelDriver(
            client=client,
            model=model,
            timeout_seconds=timeout_seconds,
        ),
    )


def _gemini_usage(response: types.GenerateContentResponse) -> ModelUsage | None:
    metadata = response.usage_metadata
    if metadata is None:
        return None
    values = {
        "input_tokens": metadata.prompt_token_count,
        "output_tokens": metadata.candidates_token_count,
        "cached_input_tokens": metadata.cached_content_token_count,
        "reasoning_tokens": metadata.thoughts_token_count,
        "total_tokens": metadata.total_token_count,
    }
    if all(value is None for value in values.values()):
        return None
    return ModelUsage(**values)


def gemini_response_schema(output_type: type[BaseModel]) -> dict[str, Any]:
    """Translate strict Pydantic validation into Gemini's schema subset.

    Gemini rejects ``additionalProperties`` even when Pydantic emits it as
    ``false`` for a closed model. Removing that provider-unsupported keyword
    affects only generation guidance; the returned payload is still validated
    against the original strict Pydantic type before it crosses the adapter.
    """

    schema = output_type.model_json_schema()
    _remove_additional_properties(schema)
    return schema


def _remove_additional_properties(value: object) -> None:
    if isinstance(value, dict):
        mapping = cast("dict[str, object]", value)
        mapping.pop("additionalProperties", None)
        for nested in mapping.values():
            _remove_additional_properties(nested)
    elif isinstance(value, list):
        for nested in value:
            _remove_additional_properties(nested)
