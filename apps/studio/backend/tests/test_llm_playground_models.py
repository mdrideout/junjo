"""Unit tests for LLM playground models (cache and API fetchers).

Only tests complex logic - basic dict/list operations are tested by Python.
"""

import time
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from app.features.llm_playground.models import (
    ModelsCache,
    fetch_anthropic_models,
    fetch_gemini_models,
    fetch_openai_models,
    get_models_for_provider,
    models_cache,
)
from app.features.llm_playground.schemas import ModelInfo


@pytest.mark.unit
def test_models_cache_expiration():
    """Test cache expiration after TTL (tests our TTL logic)."""
    cache = ModelsCache(ttl_seconds=1)  # 1 second TTL

    models = [
        ModelInfo(
            id="openai/gpt-4o",
            provider="openai",
            display_name="GPT-4o",
            supports_reasoning=False,
        )
    ]

    # Cache models
    cache.set("openai", models)

    # Should be cached
    cached = cache.get("openai")
    assert cached is not None

    # Wait for expiration
    time.sleep(1.1)

    # Should be expired
    cached = cache.get("openai")
    assert cached is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_openai_models_success():
    """Test fetching OpenAI models from API (mocked)."""
    mock_response_data = {
        "data": [
            {"id": "gpt-4o", "object": "model"},
            {"id": "gpt-4-turbo", "object": "model"},
            {"id": "o1-preview", "object": "model"},
            {"id": "whisper-1", "object": "model"},  # Should be filtered out
        ]
    }

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Mock response with synchronous json() method
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value=mock_response_data)
        mock_response.raise_for_status = Mock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.features.llm_playground.models.settings") as mock_settings:
            mock_settings.llm.openai_api_key = "sk-test-key"

            models = await fetch_openai_models()

            # Should filter to only gpt-* and o-series models
            assert len(models) == 3
            model_ids = [m.id for m in models]
            assert "openai/gpt-4o" in model_ids
            assert "openai/gpt-4-turbo" in model_ids
            assert "openai/o1-preview" in model_ids
            assert "openai/whisper-1" not in model_ids


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_openai_models_no_api_key():
    """Test fetch_openai_models raises ValueError when API key not configured."""
    with patch("app.features.llm_playground.models.settings") as mock_settings:
        mock_settings.llm.openai_api_key = None

        with pytest.raises(ValueError, match="OPENAI_API_KEY not configured"):
            await fetch_openai_models()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_openai_models_http_error():
    """Test fetch_openai_models raises HTTPError on API failure."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "Unauthorized", request=Mock(), response=mock_response
            )
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.features.llm_playground.models.settings") as mock_settings:
            mock_settings.llm.openai_api_key = "sk-test-key"

            with pytest.raises(httpx.HTTPStatusError):
                await fetch_openai_models()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_anthropic_models_success():
    """Test fetching Anthropic models from API (mocked)."""
    mock_response_data = {
        "data": [
            {
                "id": "claude-3-5-sonnet-20241022",
                "type": "model",
                "display_name": "Claude 3.5 Sonnet",
            },
            {
                "id": "claude-3-opus-20240229",
                "type": "model",
                "display_name": "Claude 3 Opus",
            },
            {
                "id": "not-a-model",
                "type": "other",  # Should be filtered out
            },
        ]
    }

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value=mock_response_data)
        mock_response.raise_for_status = Mock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.features.llm_playground.models.settings") as mock_settings:
            mock_settings.llm.anthropic_api_key = "sk-ant-test-key"

            models = await fetch_anthropic_models()

            # Should filter to only type=model
            assert len(models) == 2
            model_ids = [m.id for m in models]
            assert "anthropic/claude-3-5-sonnet-20241022" in model_ids
            assert "anthropic/claude-3-opus-20240229" in model_ids


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_anthropic_models_no_api_key():
    """Test fetch_anthropic_models raises ValueError when API key not configured."""
    with patch("app.features.llm_playground.models.settings") as mock_settings:
        mock_settings.llm.anthropic_api_key = None

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not configured"):
            await fetch_anthropic_models()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_gemini_models_success():
    """Test fetching Gemini models from API (mocked)."""
    mock_response_data = {
        "models": [
            {
                "name": "models/gemini-2.5-pro",
                "displayName": "Gemini 2.5 Pro",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/gemini-2.5-flash-lite",
                "displayName": "Gemini 1.5 Flash",
                "supportedGenerationMethods": ["generateContent", "embedContent"],
            },
            {
                "name": "models/text-embedding-004",  # Should be filtered out
                "displayName": "Text Embedding",
                "supportedGenerationMethods": ["embedContent"],
            },
            {
                "name": "models/palm-2",  # Should be filtered out (not gemini-)
                "displayName": "PaLM 2",
                "supportedGenerationMethods": ["generateContent"],
            },
        ]
    }

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value=mock_response_data)
        mock_response.raise_for_status = Mock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.features.llm_playground.models.settings") as mock_settings:
            mock_settings.llm.gemini_api_key = "test-api-key"

            models = await fetch_gemini_models()

            # Should filter to gemini-* with generateContent support
            assert len(models) == 2
            model_ids = [m.id for m in models]
            assert "gemini/gemini-2.5-pro" in model_ids
            assert "gemini/gemini-2.5-flash-lite" in model_ids
            assert "gemini/text-embedding-004" not in model_ids
            assert "gemini/palm-2" not in model_ids


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_gemini_models_no_api_key():
    """Test fetch_gemini_models raises ValueError when API key not configured."""
    with patch("app.features.llm_playground.models.settings") as mock_settings:
        mock_settings.llm.gemini_api_key = None

        with pytest.raises(ValueError, match="GEMINI_API_KEY not configured"):
            await fetch_gemini_models()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_models_for_provider_from_cache():
    """Test get_models_for_provider returns cached models."""
    # Clear cache first
    models_cache.clear()

    # Pre-populate cache
    cached_models = [
        ModelInfo(
            id="openai/gpt-4o",
            provider="openai",
            display_name="GPT-4o",
            supports_reasoning=False,
        )
    ]
    models_cache.set("openai", cached_models)

    # Should return cached models without API call
    models = await get_models_for_provider("openai")
    assert len(models) == 1
    assert models[0].id == "openai/gpt-4o"

    # Clean up
    models_cache.clear()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_models_for_provider_force_refresh():
    """Test get_models_for_provider with force_refresh=True bypasses cache."""
    # Clear cache first
    models_cache.clear()

    # Pre-populate cache
    cached_models = [
        ModelInfo(
            id="openai/gpt-4o",
            provider="openai",
            display_name="GPT-4o (cached)",
            supports_reasoning=False,
        )
    ]
    models_cache.set("openai", cached_models)

    # Mock API fetch
    with patch("app.features.llm_playground.models.fetch_openai_models") as mock_fetch:
        mock_fetch.return_value = [
            ModelInfo(
                id="openai/gpt-4o",
                provider="openai",
                display_name="GPT-4o (fresh)",
                supports_reasoning=False,
            )
        ]

        # Force refresh should bypass cache and call API
        models = await get_models_for_provider("openai", force_refresh=True)
        mock_fetch.assert_called_once()
        assert models[0].display_name == "GPT-4o (fresh)"

    # Clean up
    models_cache.clear()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_models_for_provider_invalid_provider():
    """Test get_models_for_provider raises ValueError for invalid provider."""
    with pytest.raises(ValueError, match="Invalid provider"):
        await get_models_for_provider("invalid_provider")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_models_for_provider_api_failure():
    """Test get_models_for_provider raises exception when API fails (no fallback)."""
    # Clear cache first
    models_cache.clear()

    # Mock API fetch to raise HTTPError
    with patch("app.features.llm_playground.models.fetch_openai_models") as mock_fetch:
        mock_fetch.side_effect = httpx.HTTPError("API unavailable")

        # Should raise exception (no hardcoded fallback)
        with pytest.raises(httpx.HTTPError, match="API unavailable"):
            await get_models_for_provider("openai")

    # Clean up
    models_cache.clear()
