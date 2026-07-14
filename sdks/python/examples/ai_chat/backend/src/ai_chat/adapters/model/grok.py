"""xAI Grok adapters for bounded Workflow calls and Agent decisions."""

from typing import TypeVar

from junjo import ModelDriverBinding, ModelDriverDescriptor
from junjo.agent import ModelRequest
from pydantic import BaseModel
from xai_sdk import AsyncClient
from xai_sdk.chat import system, user

from .provider_decision import ProviderDecision, provider_prompt

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class GrokLanguageModel:
    """Narrow application text capability; Agent operation translation is separate."""

    def __init__(self, *, api_key: str, model: str) -> None:
        self._client = AsyncClient(api_key=api_key)
        self._model = model

    async def generate_text(self, *, prompt: str) -> str:
        chat = self._client.chat.create(
            model=self._model,
            messages=[user(prompt)],
            store_messages=False,
        )
        response = await chat.sample()
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
        _, parsed = await chat.parse(output_type)
        return output_type.model_validate(parsed)


class GrokModelDriver:
    def __init__(self, *, api_key: str, model: str) -> None:
        self._client = AsyncClient(api_key=api_key)
        self._model = model

    async def request(self, request: ModelRequest) -> object:
        chat = self._client.chat.create(
            model=self._model,
            messages=[
                system("Return the requested structured decision without commentary."),
                user(provider_prompt(request)),
            ],
            store_messages=False,
        )
        _, parsed = await chat.parse(ProviderDecision)
        return ProviderDecision.model_validate(parsed).to_junjo()


def grok_model_binding(*, api_key: str, model: str) -> ModelDriverBinding:
    return ModelDriverBinding.per_run(
        descriptor=ModelDriverDescriptor(
            driver_key="ai_chat_grok",
            provider="xai",
            model=model,
            settings={"decision_format": "structured-json-v1"},
        ),
        factory=lambda: GrokModelDriver(api_key=api_key, model=model),
    )
