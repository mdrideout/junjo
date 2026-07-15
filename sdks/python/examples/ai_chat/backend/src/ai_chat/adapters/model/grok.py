"""xAI Grok adapters for bounded Workflow calls and Agent decisions.

The xAI SDK emits OpenTelemetry CLIENT spans for ``sample`` and ``parse``.
These adapters preserve that supported instrumentation instead of emitting a
second, competing provider span around the same operation.
"""

from typing import TypeVar

from junjo import ModelDriverBinding, ModelDriverDescriptor
from junjo.agent import ModelRequest, ModelUsage
from pydantic import BaseModel
from xai_sdk import AsyncClient
from xai_sdk.chat import Response, system, user

from ai_chat.adapters.provider_call import await_provider_call

from .provider_decision import ProviderDecision, provider_prompt

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class GrokLanguageModel:
    """Narrow application text capability; Agent operation translation is separate."""

    def __init__(
        self,
        *,
        client: AsyncClient,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def generate_text(self, *, prompt: str) -> str:
        chat = self._client.chat.create(
            model=self._model,
            messages=[user(prompt)],
            store_messages=False,
        )
        response = await await_provider_call(
            chat.sample(),
            timeout_seconds=self._timeout_seconds,
        )
        text = getattr(response, "content", None)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Grok returned no text.")
        return text.strip()

    async def generate_structured(
        self,
        *,
        prompt: str,
        output_type: type[StructuredOutput],
    ) -> StructuredOutput:
        chat = self._client.chat.create(
            model=self._model,
            messages=[
                system("Return only the requested structured value."),
                user(prompt),
            ],
            store_messages=False,
        )
        _, parsed = await await_provider_call(
            chat.parse(output_type),
            timeout_seconds=self._timeout_seconds,
        )
        return output_type.model_validate(parsed)


class GrokModelDriver:
    def __init__(
        self,
        *,
        client: AsyncClient,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def request(self, request: ModelRequest) -> object:
        chat = self._client.chat.create(
            model=self._model,
            messages=[
                system("Return the requested structured decision without commentary."),
                user(provider_prompt(request)),
            ],
            store_messages=False,
        )
        response, parsed = await await_provider_call(
            chat.parse(ProviderDecision),
            timeout_seconds=self._timeout_seconds,
        )
        return ProviderDecision.model_validate(parsed).to_junjo(
            usage=_grok_usage(response),
        )


def grok_model_binding(
    *,
    client: AsyncClient,
    model: str,
    timeout_seconds: float,
) -> ModelDriverBinding:
    return ModelDriverBinding.shared(
        descriptor=ModelDriverDescriptor(
            driver_key="ai_chat_grok",
            provider="xai",
            model=model,
            settings={
                "decision_format": "structured-json-envelope-v2",
                "timeout_seconds": timeout_seconds,
            },
        ),
        driver=GrokModelDriver(
            client=client,
            model=model,
            timeout_seconds=timeout_seconds,
        ),
    )


def _grok_usage(response: Response) -> ModelUsage | None:
    usage = response.usage
    reported = {field.name for field, _ in usage.ListFields()}
    names = {
        "prompt_tokens",
        "completion_tokens",
        "cached_prompt_text_tokens",
        "reasoning_tokens",
        "total_tokens",
    }
    if reported.isdisjoint(names):
        return None
    return ModelUsage(
        input_tokens=usage.prompt_tokens if "prompt_tokens" in reported else None,
        output_tokens=usage.completion_tokens if "completion_tokens" in reported else None,
        cached_input_tokens=(usage.cached_prompt_text_tokens if "cached_prompt_text_tokens" in reported else None),
        reasoning_tokens=(usage.reasoning_tokens if "reasoning_tokens" in reported else None),
        total_tokens=usage.total_tokens if "total_tokens" in reported else None,
    )
