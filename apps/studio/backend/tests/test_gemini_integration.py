"""Integration test for Gemini via LiteLLM."""

import pytest

from app.features.llm_playground.schemas import GenerateRequest, Message
from app.features.llm_playground.service import LLMService


@pytest.mark.integration
@pytest.mark.requires_gemini_api
@pytest.mark.asyncio
async def test_gemini_generation(mock_authenticated_user):
    """Test Gemini model generation through LiteLLM.

    Requires GEMINI_API_KEY in .env or environment variables.
    """
    request = GenerateRequest(
        model="gemini/gemini-2.5-flash-lite",
        messages=[Message(role="user", content="Say hello in exactly 3 words.")],
        temperature=0.7,
        max_tokens=10,
    )

    response = await LLMService.generate(request, authenticated_user=mock_authenticated_user)

    # Verify response structure
    assert response.id is not None
    assert response.model is not None
    assert len(response.choices) == 1
    assert response.choices[0].message.content is not None
    assert len(response.choices[0].message.content) > 0
    print(f"✓ Gemini response: {response.choices[0].message.content}")
