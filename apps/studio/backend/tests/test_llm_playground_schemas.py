"""Unit tests for LLM playground schemas.

Only tests custom validation logic - basic Pydantic behavior is tested by the framework.
"""

import pytest
from pydantic import ValidationError

from app.features.llm_playground.schemas import GenerateRequest, Message


@pytest.mark.unit
def test_generate_request_temperature_bounds():
    """Test GenerateRequest validates temperature bounds (custom validation)."""
    # Valid temperature
    req = GenerateRequest(
        model="openai/gpt-4o",
        messages=[Message(role="user", content="Hello")],
        temperature=0.5,
    )
    assert req.temperature == 0.5

    # Invalid temperature (too high)
    with pytest.raises(ValidationError):
        GenerateRequest(
            model="openai/gpt-4o",
            messages=[Message(role="user", content="Hello")],
            temperature=2.5,
        )

    # Invalid temperature (negative)
    with pytest.raises(ValidationError):
        GenerateRequest(
            model="openai/gpt-4o",
            messages=[Message(role="user", content="Hello")],
            temperature=-0.5,
        )
