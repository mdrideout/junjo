"""Simple integration test for Gemini via LiteLLM (no pytest needed)."""

import asyncio
import sys

from app.features.llm_playground.schemas import GenerateRequest, Message
from app.features.llm_playground.service import LLMService


async def test_gemini():
    """Test Gemini model generation through LiteLLM."""
    print("Testing Gemini generation...")
    print("=" * 60)

    request = GenerateRequest(
        model="gemini/gemini-2.5-flash-lite",
        messages=[Message(role="user", content="Say hello in exactly 3 words.")],
        temperature=0.7,
        max_tokens=10,
    )

    try:
        response = await LLMService.generate(request)

        # Verify response
        assert response.id is not None, "Response ID is None"
        assert response.model is not None, "Response model is None"
        assert len(response.choices) == 1, f"Expected 1 choice, got {len(response.choices)}"
        assert response.choices[0].message.content is not None, "Message content is None"
        assert len(response.choices[0].message.content) > 0, "Message content is empty"

        print("\n✓ SUCCESS!")
        print(f"  Model: {response.model}")
        print(f"  Response: {response.choices[0].message.content}")
        print(f"  Tokens: {response.usage.total_tokens if response.usage else 'N/A'}")
        print("=" * 60)
        return 0

    except Exception as e:
        print("\n✗ FAILED!")
        print(f"  Error: {e}")
        import traceback

        traceback.print_exc()
        print("=" * 60)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_gemini())
    sys.exit(exit_code)
