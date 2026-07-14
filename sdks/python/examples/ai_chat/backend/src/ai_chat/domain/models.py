"""Portable typed values owned by the chat application."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DomainModel(BaseModel):
    """Immutable base for values crossing application boundaries."""

    model_config = ConfigDict(frozen=True)


class MessageRole(StrEnum):
    """The two persisted roles used by this bounded chat example."""

    USER = "user"
    ASSISTANT = "assistant"


class Conversation(DomainModel):
    id: str
    title: str
    contact_id: str


class ContactProfile(DomainModel):
    id: str
    display_name: str
    bio: str


class ImageArtifact(DomainModel):
    id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    alt_text: str = Field(min_length=1)


class ChatMessage(DomainModel):
    id: str
    turn_id: str
    conversation_id: str
    role: MessageRole
    content: str
    image: ImageArtifact | None = None
    created_at: datetime


class CompletedTurn(DomainModel):
    user: ChatMessage
    assistant: ChatMessage


class ChatAgentInput(DomainModel):
    conversation_id: str
    turn_id: str
    message: str = Field(min_length=1, max_length=2_500)


class ChatAgentOutput(DomainModel):
    message: str = Field(min_length=1, max_length=2_500)
    image: ImageArtifact | None = None


class SearchHistoryInput(DomainModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=20)


class HistoryMatch(DomainModel):
    turn_id: str
    role: MessageRole
    content: str


class SearchHistoryOutput(DomainModel):
    matches: tuple[HistoryMatch, ...]


class ContactProfileInput(DomainModel):
    include_bio: bool = True


class ContactProfileOutput(DomainModel):
    display_name: str
    bio: str | None


class CreateImageInput(DomainModel):
    prompt: str = Field(min_length=1, max_length=500)


class CreateImageOutput(DomainModel):
    artifact: ImageArtifact


class TurnResult(DomainModel):
    conversation_id: str
    workflow_run_id: str
    agent_run_id: str
    user_message: ChatMessage
    assistant_message: ChatMessage
