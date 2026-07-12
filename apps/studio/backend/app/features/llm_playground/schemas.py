"""
LLM Playground Schemas.

Pydantic models for request/response validation and serialization.
"""

from typing import Any

from pydantic import BaseModel, Field


class Message(BaseModel):
    """Chat message."""

    role: str = Field(..., description="Role: 'system', 'user', or 'assistant'")
    content: str = Field(..., description="Message content")


class GenerateRequest(BaseModel):
    """
    Unified LLM generation request.

    Model names use provider prefixes for LiteLLM routing:
    - openai/gpt-4o, openai/o1, openai/o3-mini
    - anthropic/claude-3-5-sonnet-20241022, anthropic/claude-3-7-sonnet-20250219
    - gemini/gemini-2.5-pro, gemini/gemini-2.5-flash
    """

    model: str = Field(
        ...,
        description="Model with provider prefix (e.g., 'gemini/gemini-2.5-flash', 'openai/gpt-4o')",
        pattern=r"^[a-z_]+/[a-z0-9._-]+$",
    )
    messages: list[Message] = Field(..., description="Chat messages")

    # Common generation parameters
    temperature: float | None = Field(None, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int | None = Field(None, gt=0, description="Maximum tokens to generate")
    top_p: float | None = Field(None, ge=0.0, le=1.0, description="Nucleus sampling parameter")
    stop: list[str] | None = Field(None, max_length=4, description="Stop sequences")

    # Reasoning/thinking (unified - LiteLLM translates to provider-specific)
    reasoning_effort: str | None = Field(
        None,
        description="Reasoning effort: 'minimal', 'low', 'medium', 'high'. Auto-translates to provider thinking.",
        pattern="^(minimal|low|medium|high)$",
    )

    # OpenAI-specific (for reasoning models)
    max_completion_tokens: int | None = Field(
        None, gt=0, description="Max completion tokens (OpenAI reasoning models)"
    )

    # JSON mode / Structured outputs
    json_mode: bool = Field(False, description="Enable JSON output mode")
    json_schema: dict[str, Any] | None = Field(
        None, description="JSON schema for structured output"
    )


class Usage(BaseModel):
    """Token usage information."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class Choice(BaseModel):
    """Generation choice."""

    index: int
    message: Message
    finish_reason: str | None = None


class GenerateResponse(BaseModel):
    """
    LLM generation response (OpenAI-compatible format).

    LiteLLM returns responses in OpenAI format regardless of provider.
    """

    id: str
    object: str
    created: int
    model: str
    choices: list[Choice]
    usage: Usage | None = None
    reasoning_content: str | None = Field(
        None, description="Thinking/reasoning content for reasoning models"
    )


# Model discovery schemas


class ModelInfo(BaseModel):
    """Model information."""

    id: str = Field(..., description="Full model name with prefix (e.g., 'openai/gpt-4o')")
    provider: str = Field(..., description="Provider name: 'openai', 'anthropic', 'gemini'")
    display_name: str = Field(..., description="Human-readable model name")
    supports_reasoning: bool = Field(False, description="Supports reasoning/thinking")
    supports_vision: bool = Field(False, description="Supports vision/image inputs")
    max_tokens: int | None = Field(None, description="Maximum context tokens")


class ModelsResponse(BaseModel):
    """Model listing response."""

    models: list[ModelInfo]
