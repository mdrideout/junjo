"""Integration tests for LLM playground router."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.features.llm_playground.models import models_cache
from app.features.llm_playground.schemas import ModelInfo
from app.main import app


@pytest.fixture(autouse=True)
async def clear_cache():
    """Clear models cache before each test."""
    models_cache.clear()
    yield
    models_cache.clear()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_unauthenticated():
    """Test /llm/generate requires authentication."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/llm/generate",
            json={
                "model": "openai/gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )
        assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_authenticated():
    """Test /llm/generate with authentication."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )
        session_cookie = sign_in_response.cookies["session"]

        # Mock LiteLLM response
        mock_message = AsyncMock(role="assistant", content="Hello! How can I help?")
        mock_message.reasoning_content = None
        mock_message.thinking_blocks = None

        mock_choice = AsyncMock(index=0, finish_reason="stop")
        mock_choice.message = mock_message

        mock_response = AsyncMock()
        mock_response.id = "chatcmpl-123"
        mock_response.object = "chat.completion"
        mock_response.created = 1234567890
        mock_response.model = "openai/gpt-4o"
        mock_response.choices = [mock_choice]
        mock_response.usage = AsyncMock(
            prompt_tokens=5,
            completion_tokens=10,
            total_tokens=15,
        )

        with patch("app.features.llm_playground.service.acompletion", return_value=mock_response):
            response = await client.post(
                "/llm/generate",
                json={
                    "model": "openai/gpt-4o",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                cookies={"session": session_cookie},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "chatcmpl-123"
            assert data["model"] == "openai/gpt-4o"
            assert len(data["choices"]) == 1
            assert data["choices"][0]["message"]["content"] == "Hello! How can I help?"
            assert data["usage"]["total_tokens"] == 15


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_with_reasoning():
    """Test /llm/generate with reasoning model."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )
        session_cookie = sign_in_response.cookies["session"]

        # Mock LiteLLM response with reasoning on message
        mock_message = AsyncMock(role="assistant", content="Solution: 42")
        mock_message.reasoning_content = "Let me think about this problem..."  # On message!
        mock_message.thinking_blocks = None

        mock_choice = AsyncMock(index=0, finish_reason="stop")
        mock_choice.message = mock_message

        mock_response = AsyncMock()
        mock_response.id = "chatcmpl-456"
        mock_response.object = "chat.completion"
        mock_response.created = 1234567890
        mock_response.model = "openai/o1-preview"
        mock_response.choices = [mock_choice]
        mock_response.usage = AsyncMock(
            prompt_tokens=10,
            completion_tokens=50,
            total_tokens=60,
        )

        with patch("app.features.llm_playground.service.acompletion", return_value=mock_response):
            response = await client.post(
                "/llm/generate",
                json={
                    "model": "openai/o1-preview",
                    "messages": [{"role": "user", "content": "What is the answer?"}],
                    "reasoning_effort": "high",
                },
                cookies={"session": session_cookie},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["reasoning_content"] == "Let me think about this problem..."
            assert data["choices"][0]["message"]["content"] == "Solution: 42"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_invalid_request():
    """Test /llm/generate with invalid request data."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )
        session_cookie = sign_in_response.cookies["session"]

        # Missing required field (messages)
        response = await client.post(
            "/llm/generate",
            json={"model": "openai/gpt-4o"},
            cookies={"session": session_cookie},
        )
        assert response.status_code == 422  # Validation error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_provider_models_unauthenticated():
    """Test /llm/providers/{provider}/models requires authentication."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/llm/providers/openai/models")
        assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_provider_models_invalid_provider():
    """Test /llm/providers/{provider}/models with invalid provider."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )
        session_cookie = sign_in_response.cookies["session"]

        response = await client.get(
            "/llm/providers/invalid/models",
            cookies={"session": session_cookie},
        )
        assert response.status_code == 400
        assert "Invalid provider" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_provider_models_openai():
    """Test /llm/providers/openai/models endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )
        session_cookie = sign_in_response.cookies["session"]

        # Mock fetch_openai_models
        mock_models = [
            ModelInfo(
                id="openai/gpt-4o",
                provider="openai",
                display_name="GPT-4o",
                supports_reasoning=False,
            ),
            ModelInfo(
                id="openai/o1-preview",
                provider="openai",
                display_name="o1-preview",
                supports_reasoning=True,
            ),
        ]

        with patch(
            "app.features.llm_playground.router.get_models_for_provider",
            return_value=mock_models,
        ):
            response = await client.get(
                "/llm/providers/openai/models",
                cookies={"session": session_cookie},
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["models"]) == 2
            assert data["models"][0]["id"] == "openai/gpt-4o"
            assert data["models"][1]["id"] == "openai/o1-preview"
            assert data["models"][1]["supports_reasoning"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_provider_models_anthropic():
    """Test /llm/providers/anthropic/models endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )
        session_cookie = sign_in_response.cookies["session"]

        # Mock fetch_anthropic_models
        mock_models = [
            ModelInfo(
                id="anthropic/claude-3-5-sonnet-20241022",
                provider="anthropic",
                display_name="Claude 3.5 Sonnet",
                supports_reasoning=True,
            ),
        ]

        with patch(
            "app.features.llm_playground.router.get_models_for_provider",
            return_value=mock_models,
        ):
            response = await client.get(
                "/llm/providers/anthropic/models",
                cookies={"session": session_cookie},
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["models"]) == 1
            assert data["models"][0]["provider"] == "anthropic"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_provider_models_gemini():
    """Test /llm/providers/gemini/models endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )
        session_cookie = sign_in_response.cookies["session"]

        # Mock fetch_gemini_models
        mock_models = [
            ModelInfo(
                id="gemini/gemini-2.5-pro",
                provider="gemini",
                display_name="Gemini 2.5 Pro",
                supports_reasoning=True,
            ),
        ]

        with patch(
            "app.features.llm_playground.router.get_models_for_provider",
            return_value=mock_models,
        ):
            response = await client.get(
                "/llm/providers/gemini/models",
                cookies={"session": session_cookie},
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["models"]) == 1
            assert data["models"][0]["provider"] == "gemini"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_provider_models_no_api_key():
    """Test /llm/providers/{provider}/models when API key not configured."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )
        session_cookie = sign_in_response.cookies["session"]

        # Mock get_models_for_provider to raise ValueError
        with patch(
            "app.features.llm_playground.router.get_models_for_provider",
            side_effect=ValueError("OPENAI_API_KEY not configured"),
        ):
            response = await client.get(
                "/llm/providers/openai/models",
                cookies={"session": session_cookie},
            )

            assert response.status_code == 500
            assert "OPENAI_API_KEY not configured" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_provider_models_api_failure():
    """Test /llm/providers/{provider}/models when provider API fails."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )
        session_cookie = sign_in_response.cookies["session"]

        # Mock get_models_for_provider to raise HTTPError
        with patch(
            "app.features.llm_playground.router.get_models_for_provider",
            side_effect=httpx.HTTPError("API unavailable"),
        ):
            response = await client.get(
                "/llm/providers/openai/models",
                cookies={"session": session_cookie},
            )

            assert response.status_code == 500
            assert "Failed to fetch models" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_refresh_provider_models():
    """Test /llm/providers/{provider}/models/refresh endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )
        session_cookie = sign_in_response.cookies["session"]

        # Mock get_models_for_provider
        mock_models = [
            ModelInfo(
                id="openai/gpt-4o",
                provider="openai",
                display_name="GPT-4o (refreshed)",
                supports_reasoning=False,
            ),
        ]

        with patch(
            "app.features.llm_playground.router.get_models_for_provider",
            return_value=mock_models,
        ) as mock_get_models:
            response = await client.post(
                "/llm/providers/openai/models/refresh",
                cookies={"session": session_cookie},
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["models"]) == 1
            assert data["models"][0]["display_name"] == "GPT-4o (refreshed)"

            # Verify force_refresh=True was passed
            mock_get_models.assert_called_once_with("openai", force_refresh=True)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_refresh_provider_models_invalid_provider():
    """Test /llm/providers/{provider}/models/refresh with invalid provider."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )
        session_cookie = sign_in_response.cookies["session"]

        response = await client.post(
            "/llm/providers/invalid/models/refresh",
            cookies={"session": session_cookie},
        )
        assert response.status_code == 400
        assert "Invalid provider" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_refresh_provider_models_unauthenticated():
    """Test /llm/providers/{provider}/models/refresh requires authentication."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/llm/providers/openai/models/refresh")
        assert response.status_code == 401
