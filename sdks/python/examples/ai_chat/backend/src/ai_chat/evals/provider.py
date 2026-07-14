"""Explicit live provider composition for AI Chat evals."""

from ai_chat.adapters.model import GeminiLanguageModel, GrokLanguageModel
from ai_chat.config import ModelProvider, Settings
from ai_chat.domain.ports import LanguageModel


def live_language_model() -> tuple[Settings, LanguageModel]:
    settings = Settings.from_environment()
    if settings.model_provider is ModelProvider.GEMINI:
        assert settings.gemini_api_key is not None
        return settings, GeminiLanguageModel(
            api_key=settings.gemini_api_key,
            model=settings.gemini_text_model,
        )
    assert settings.xai_api_key is not None
    return settings, GrokLanguageModel(
        api_key=settings.xai_api_key,
        model=settings.grok_text_model,
    )
