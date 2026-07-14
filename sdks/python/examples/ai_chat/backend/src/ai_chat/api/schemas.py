"""Strict API projections; domain internals do not leak over HTTP."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_chat.domain.models import ChatMessage, Conversation, TurnResult


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentErrorResponse(ApiModel):
    detail: str
    agent_run_id: str
    termination_reason: str


class ConversationSummary(ApiModel):
    id: str
    title: str

    @classmethod
    def from_domain(cls, conversation: Conversation) -> ConversationSummary:
        return cls(id=conversation.id, title=conversation.title)


class ConversationListResponse(ApiModel):
    conversations: tuple[ConversationSummary, ...]


class MessageResponse(ApiModel):
    id: str
    turn_id: str
    role: Literal["user", "assistant"]
    content: str
    image_url: str | None
    image_alt: str | None
    created_at: datetime

    @model_validator(mode="after")
    def image_fields_are_complete(self) -> MessageResponse:
        if (self.image_url is None) != (self.image_alt is None):
            raise ValueError("image_url and image_alt must both be present or both be null.")
        if self.image_alt is not None and not self.image_alt.strip():
            raise ValueError("image_alt must be nonempty when an image is present.")
        return self

    @classmethod
    def from_domain(cls, message: ChatMessage) -> MessageResponse:
        return cls(
            id=message.id,
            turn_id=message.turn_id,
            role=message.role.value,
            content=message.content,
            image_url=message.image.url if message.image is not None else None,
            image_alt=message.image.alt_text if message.image is not None else None,
            created_at=message.created_at,
        )


class MessageListResponse(ApiModel):
    conversation_id: str
    messages: tuple[MessageResponse, ...]


class SubmitTurnRequest(ApiModel):
    text: str = Field(min_length=1, max_length=2_500)

    @field_validator("text")
    @classmethod
    def text_is_meaningful(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text must contain a non-whitespace character.")
        return normalized


class SubmitTurnResponse(ApiModel):
    conversation_id: str
    workflow_run_id: str
    agent_run_id: str
    user_message: MessageResponse
    assistant_message: MessageResponse

    @classmethod
    def from_domain(cls, result: TurnResult) -> SubmitTurnResponse:
        return cls(
            conversation_id=result.conversation_id,
            workflow_run_id=result.workflow_run_id,
            agent_run_id=result.agent_run_id,
            user_message=MessageResponse.from_domain(result.user_message),
            assistant_message=MessageResponse.from_domain(result.assistant_message),
        )
