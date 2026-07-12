"""
Model discovery and caching (2-tier strategy).

Strategy:
1. Check cache (15-minute TTL)
2. Fetch from provider API if cache miss or expired
3. Fail explicitly if API unavailable (no hardcoded fallback)
"""

import time
from typing import Any

import httpx
from litellm import supports_reasoning
from loguru import logger

from app.config.settings import settings
from app.features.llm_playground.schemas import ModelInfo


class ModelsCache:
    """
    In-memory cache for provider models with TTL.

    Default TTL: 15 minutes (900 seconds)
    """

    def __init__(self, ttl_seconds: int = 900):
        """
        Initialize cache.

        Args:
            ttl_seconds: Time-to-live in seconds (default: 900 = 15 minutes)
        """
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[list[ModelInfo], float]] = {}

    def get(self, provider: str) -> list[ModelInfo] | None:
        """
        Get cached models if not expired.

        Args:
            provider: Provider name (openai, anthropic, gemini)

        Returns:
            List of models if cached and not expired, None otherwise
        """
        if provider not in self._cache:
            return None

        models, timestamp = self._cache[provider]

        # Check if expired
        if time.time() - timestamp > self.ttl_seconds:
            logger.debug(f"Cache expired for {provider}")
            del self._cache[provider]
            return None

        logger.debug(f"Cache hit for {provider}")
        return models

    def set(self, provider: str, models: list[ModelInfo]) -> None:
        """
        Cache models with current timestamp.

        Args:
            provider: Provider name
            models: List of models to cache
        """
        self._cache[provider] = (models, time.time())
        logger.debug(f"Cached {len(models)} models for {provider}")

    def clear(self, provider: str | None = None) -> None:
        """
        Clear cache for a provider or all providers.

        Args:
            provider: Provider name, or None to clear all
        """
        if provider:
            self._cache.pop(provider, None)
            logger.debug(f"Cleared cache for {provider}")
        else:
            self._cache.clear()
            logger.debug("Cleared all cache")


# Global cache instance
models_cache = ModelsCache()


async def fetch_openai_models() -> list[ModelInfo]:
    """
    Fetch models from OpenAI API.

    Returns:
        List of OpenAI models with metadata

    Raises:
        httpx.HTTPError: If API request fails
    """
    if not settings.llm.openai_api_key:
        raise ValueError("OPENAI_API_KEY not configured")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {settings.llm.openai_api_key}"},
            timeout=10.0,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()

        models: list[ModelInfo] = []
        for model in data.get("data", []):
            model_id: str = model.get("id", "")

            # Filter to GPT models and o-series reasoning models
            if model_id.startswith(("gpt-", "o1", "o3", "o4")):
                full_id = f"openai/{model_id}"

                # Check reasoning support using LiteLLM
                reasoning_support = supports_reasoning(full_id)

                models.append(
                    ModelInfo(
                        id=full_id,
                        provider="openai",
                        display_name=model_id,
                        supports_reasoning=reasoning_support,
                        supports_vision=False,
                        max_tokens=None,
                    )
                )

        logger.info(f"Fetched {len(models)} models from OpenAI API")
        return models


async def fetch_anthropic_models() -> list[ModelInfo]:
    """
    Fetch models from Anthropic API.

    Returns:
        List of Anthropic models with metadata

    Raises:
        httpx.HTTPError: If API request fails
    """
    if not settings.llm.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": settings.llm.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()

        models: list[ModelInfo] = []
        for model in data.get("data", []):
            if model.get("type") == "model":
                model_id: str = model.get("id", "")
                full_id = f"anthropic/{model_id}"

                # Check reasoning support using LiteLLM
                reasoning_support = supports_reasoning(full_id)

                models.append(
                    ModelInfo(
                        id=full_id,
                        provider="anthropic",
                        display_name=model.get("display_name", model_id),
                        supports_reasoning=reasoning_support,
                        supports_vision=False,
                        max_tokens=None,
                    )
                )

        logger.info(f"Fetched {len(models)} models from Anthropic API")
        return models


async def fetch_gemini_models() -> list[ModelInfo]:
    """
    Fetch models from Google AI Studio API.

    Returns:
        List of Gemini models with metadata

    Raises:
        httpx.HTTPError: If API request fails
    """
    if not settings.llm.gemini_api_key:
        raise ValueError("GEMINI_API_KEY not configured")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={settings.llm.gemini_api_key}",
            timeout=10.0,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()

        models: list[ModelInfo] = []
        for model in data.get("models", []):
            model_name: str = model.get("name", "").replace("models/", "")

            # Filter to gemini models that support generateContent
            if model_name.startswith("gemini-") and "generateContent" in model.get(
                "supportedGenerationMethods", []
            ):
                full_id = f"gemini/{model_name}"

                # Check reasoning support using LiteLLM
                reasoning_support = supports_reasoning(full_id)

                models.append(
                    ModelInfo(
                        id=full_id,
                        provider="gemini",
                        display_name=model.get("displayName", model_name),
                        supports_reasoning=reasoning_support,
                        supports_vision=False,
                        max_tokens=None,
                    )
                )

        logger.info(f"Fetched {len(models)} models from Gemini API")
        return models


async def get_models_for_provider(provider: str, force_refresh: bool = False) -> list[ModelInfo]:
    """
    Get models for provider using 2-tier strategy.

    Strategy:
    1. Check cache (15-minute TTL)
    2. Fetch from provider API

    No hardcoded fallback - fails explicitly if API unavailable.

    Args:
        provider: Provider name (openai, anthropic, gemini)
        force_refresh: Skip cache and force API fetch

    Returns:
        List of models

    Raises:
        ValueError: If provider invalid or API key not configured
        httpx.HTTPError: If API request fails
    """
    # Tier 1: Check cache
    if not force_refresh:
        cached = models_cache.get(provider)
        if cached:
            return cached

    # Tier 2: Fetch from provider API
    logger.info(f"Fetching models from {provider} API")

    if provider == "openai":
        models = await fetch_openai_models()
    elif provider == "anthropic":
        models = await fetch_anthropic_models()
    elif provider == "gemini":
        models = await fetch_gemini_models()
    else:
        raise ValueError(f"Invalid provider: {provider}")

    # Cache the results
    models_cache.set(provider, models)

    return models
