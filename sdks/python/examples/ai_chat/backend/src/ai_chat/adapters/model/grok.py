"""xAI Grok ModelDriver adapter."""

from junjo import ModelDriverBinding, ModelDriverDescriptor
from junjo.agent import ModelRequest
from xai_sdk import AsyncClient
from xai_sdk.chat import system, user

from .provider_decision import ProviderDecision, provider_prompt


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
