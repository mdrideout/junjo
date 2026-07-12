"""Unit tests for LLM playground service."""

from unittest.mock import AsyncMock, patch

import pytest

from app.features.llm_playground.schemas import (
    GenerateRequest,
    Message,
)
from app.features.llm_playground.service import LLMService


@pytest.mark.unit
def test_prepare_response_format_none():
    """Test _prepare_response_format returns None when json_mode is False."""
    result = LLMService._prepare_response_format(json_mode=False, json_schema=None)
    assert result is None


@pytest.mark.unit
def test_prepare_response_format_json_object():
    """Test _prepare_response_format returns json_object format."""
    result = LLMService._prepare_response_format(json_mode=True, json_schema=None)
    assert result == {"type": "json_object"}


@pytest.mark.unit
def test_prepare_response_format_json_schema():
    """Test _prepare_response_format returns json_schema format with strict mode."""
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    result = LLMService._prepare_response_format(json_mode=True, json_schema=schema)

    assert result["type"] == "json_schema"
    assert result["json_schema"]["name"] == "response_schema"
    assert result["json_schema"]["strict"] is True
    assert result["json_schema"]["schema"] == schema


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_minimal_request(mock_authenticated_user):
    """Test generate with minimal request parameters."""
    request = GenerateRequest(
        model="openai/gpt-4o",
        messages=[Message(role="user", content="Hello")],
    )

    # Mock litellm response
    # Create message mock with reasoning_content on it
    mock_message = AsyncMock(role="assistant", content="Hi there!")
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
        response = await LLMService.generate(request, authenticated_user=mock_authenticated_user)

        assert response.id == "chatcmpl-123"
        assert response.model == "openai/gpt-4o"
        assert len(response.choices) == 1
        assert response.choices[0].message.content == "Hi there!"
        assert response.usage.total_tokens == 15
        assert response.reasoning_content is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_with_reasoning_openai(mock_authenticated_user):
    """Test generate with OpenAI reasoning model (o1/o3/o4 series)."""
    request = GenerateRequest(
        model="openai/o1-preview",
        messages=[Message(role="user", content="Solve this problem")],
        reasoning_effort="high",
    )

    # Mock litellm response with reasoning_content on message
    mock_message = AsyncMock(role="assistant", content="Here's the solution")
    mock_message.reasoning_content = "Let me think step by step..."  # On message!
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
        response = await LLMService.generate(request, authenticated_user=mock_authenticated_user)

        assert response.reasoning_content == "Let me think step by step..."
        assert response.choices[0].message.content == "Here's the solution"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_with_reasoning_anthropic(mock_authenticated_user):
    """Test generate with Anthropic extended thinking."""
    request = GenerateRequest(
        model="anthropic/claude-3-5-sonnet-20241022",
        messages=[Message(role="user", content="Analyze this")],
        reasoning_effort="medium",
    )

    # Mock litellm response with thinking_blocks on message
    mock_message = AsyncMock(role="assistant", content="Analysis complete")
    mock_message.reasoning_content = None
    mock_message.thinking_blocks = [  # thinking_blocks on message!
        {"type": "thinking", "thinking": "First, I'll consider..."},
        {"type": "thinking", "thinking": "Then, I'll analyze..."},
    ]

    mock_choice = AsyncMock(index=0, finish_reason="end_turn")
    mock_choice.message = mock_message

    mock_response = AsyncMock()
    mock_response.id = "msg_789"
    mock_response.object = "chat.completion"
    mock_response.created = 1234567890
    mock_response.model = "anthropic/claude-3-5-sonnet-20241022"
    mock_response.choices = [mock_choice]
    mock_response.usage = AsyncMock(
        prompt_tokens=15,
        completion_tokens=30,
        total_tokens=45,
    )

    with patch("app.features.llm_playground.service.acompletion", return_value=mock_response):
        response = await LLMService.generate(request, authenticated_user=mock_authenticated_user)

        # Should concatenate thinking blocks
        assert "First, I'll consider..." in response.reasoning_content
        assert "Then, I'll analyze..." in response.reasoning_content
        assert response.choices[0].message.content == "Analysis complete"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_with_all_parameters(mock_authenticated_user):
    """Test generate with all optional parameters."""
    request = GenerateRequest(
        model="openai/gpt-4o",
        messages=[
            Message(role="system", content="You are helpful"),
            Message(role="user", content="Hello"),
        ],
        temperature=0.7,
        max_tokens=1000,
        top_p=0.9,
        stop=["END"],
        max_completion_tokens=2000,
    )

    # Create mock choice with explicit attributes
    mock_message = AsyncMock(role="assistant", content="Response")
    mock_message.reasoning_content = None
    mock_message.thinking_blocks = None

    mock_choice = AsyncMock(index=0, finish_reason="stop")
    mock_choice.message = mock_message

    mock_response = AsyncMock()
    mock_response.id = "chatcmpl-999"
    mock_response.object = "chat.completion"
    mock_response.created = 1234567890
    mock_response.model = "openai/gpt-4o"
    mock_response.choices = [mock_choice]
    mock_response.usage = None

    with patch("app.features.llm_playground.service.acompletion") as mock_acompletion:
        mock_acompletion.return_value = mock_response

        response = await LLMService.generate(request, authenticated_user=mock_authenticated_user)

        # Verify acompletion was called with correct kwargs
        call_kwargs = mock_acompletion.call_args[1]
        assert call_kwargs["model"] == "openai/gpt-4o"
        assert len(call_kwargs["messages"]) == 2
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["max_tokens"] == 1000
        assert call_kwargs["top_p"] == 0.9
        assert call_kwargs["stop"] == ["END"]
        assert call_kwargs["max_completion_tokens"] == 2000

        assert response.id == "chatcmpl-999"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_with_json_mode(mock_authenticated_user):
    """Test generate with JSON mode."""
    request = GenerateRequest(
        model="openai/gpt-4o",
        messages=[Message(role="user", content="Generate JSON")],
        json_mode=True,
    )

    # Create mock choice with explicit attributes
    mock_message = AsyncMock(role="assistant", content='{"result": "success"}')
    mock_message.reasoning_content = None
    mock_message.thinking_blocks = None

    mock_choice = AsyncMock(index=0, finish_reason="stop")
    mock_choice.message = mock_message

    mock_response = AsyncMock()
    mock_response.id = "chatcmpl-json"
    mock_response.object = "chat.completion"
    mock_response.created = 1234567890
    mock_response.model = "openai/gpt-4o"
    mock_response.choices = [mock_choice]
    mock_response.usage = None

    with patch("app.features.llm_playground.service.acompletion") as mock_acompletion:
        mock_acompletion.return_value = mock_response

        response = await LLMService.generate(request, authenticated_user=mock_authenticated_user)

        # Verify response_format was passed
        call_kwargs = mock_acompletion.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}

        assert response.choices[0].message.content == '{"result": "success"}'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_with_json_schema(mock_authenticated_user):
    """Test generate with JSON schema (structured output)."""
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }

    request = GenerateRequest(
        model="openai/gpt-4o",
        messages=[Message(role="user", content="Generate structured data")],
        json_mode=True,
        json_schema=schema,
    )

    # Create mock choice with explicit attributes
    mock_message = AsyncMock(role="assistant", content='{"name": "John"}')
    mock_message.reasoning_content = None
    mock_message.thinking_blocks = None

    mock_choice = AsyncMock(index=0, finish_reason="stop")
    mock_choice.message = mock_message

    mock_response = AsyncMock()
    mock_response.id = "chatcmpl-schema"
    mock_response.object = "chat.completion"
    mock_response.created = 1234567890
    mock_response.model = "openai/gpt-4o"
    mock_response.choices = [mock_choice]
    mock_response.usage = None

    with patch("app.features.llm_playground.service.acompletion") as mock_acompletion:
        mock_acompletion.return_value = mock_response

        response = await LLMService.generate(request, authenticated_user=mock_authenticated_user)

        # Verify response_format includes json_schema
        call_kwargs = mock_acompletion.call_args[1]
        assert call_kwargs["response_format"]["type"] == "json_schema"
        assert call_kwargs["response_format"]["json_schema"]["strict"] is True
        assert call_kwargs["response_format"]["json_schema"]["schema"] == schema

        assert response.choices[0].message.content == '{"name": "John"}'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_handles_null_content(mock_authenticated_user):
    """Test generate handles null content from LiteLLM (edge case)."""
    request = GenerateRequest(
        model="openai/gpt-4o",
        messages=[Message(role="user", content="Hello")],
    )

    # Create mock choice with explicit attributes
    mock_message = AsyncMock(role="assistant", content=None)  # Null content
    mock_message.reasoning_content = None
    mock_message.thinking_blocks = None

    mock_choice = AsyncMock(index=0, finish_reason="length")
    mock_choice.message = mock_message

    mock_response = AsyncMock()
    mock_response.id = "chatcmpl-null"
    mock_response.object = "chat.completion"
    mock_response.created = 1234567890
    mock_response.model = "openai/gpt-4o"
    mock_response.choices = [mock_choice]
    mock_response.usage = None

    with patch("app.features.llm_playground.service.acompletion", return_value=mock_response):
        response = await LLMService.generate(request, authenticated_user=mock_authenticated_user)

        # Should convert None to empty string
        assert response.choices[0].message.content == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_exception_handling(mock_authenticated_user):
    """Test generate raises exception on LiteLLM failure."""
    request = GenerateRequest(
        model="openai/gpt-4o",
        messages=[Message(role="user", content="Hello")],
    )

    with patch("app.features.llm_playground.service.acompletion") as mock_acompletion:
        mock_acompletion.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            await LLMService.generate(request, authenticated_user=mock_authenticated_user)
