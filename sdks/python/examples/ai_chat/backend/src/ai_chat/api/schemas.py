"""Strict Turn-oriented HTTP projections; domain internals remain private."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_chat.config import DebugSettings
from ai_chat.domain.models import (
    ChatMessage,
    ContactProfile,
    ContactSex,
    ConversationOverview,
    Turn,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContactResponse(ApiModel):
    id: str
    first_name: str
    last_name: str
    sex: Literal["male", "female"]
    age: int
    city: str
    state: str
    bio: str
    avatar_url: str

    @classmethod
    def from_domain(cls, contact: ContactProfile) -> ContactResponse:
        return cls(
            id=contact.id,
            first_name=contact.first_name,
            last_name=contact.last_name,
            sex=contact.sex.value,
            age=contact.age,
            city=contact.city,
            state=contact.state,
            bio=contact.bio,
            avatar_url=contact.avatar.url,
        )


class ConversationSummary(ApiModel):
    id: str
    title: str
    contact: ContactResponse
    last_message_at: datetime | None

    @classmethod
    def from_domain(cls, overview: ConversationOverview) -> ConversationSummary:
        return cls(
            id=overview.conversation.id,
            title=overview.conversation.title,
            contact=ContactResponse.from_domain(overview.contact),
            last_message_at=overview.last_message_at,
        )


class ConversationListResponse(ApiModel):
    conversations: tuple[ConversationSummary, ...]


class CreateContactRequest(ApiModel):
    sex: ContactSex


class CreateContactResponse(ApiModel):
    conversation: ConversationSummary


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


class ContextPolicyResponse(ApiModel):
    id: Literal["recent-completed-turns"]
    version: Literal[1]
    recent_turn_limit: int


class ExecutionReferencesResponse(ApiModel):
    workflow_run_id: str | None
    agent_run_id: str | None


class TurnFailureResponse(ApiModel):
    code: str
    detail: str
    termination_reason: str | None


class TurnResponse(ApiModel):
    object_type: Literal["ai_chat.turn"]
    schema_version: Literal[1]
    id: str
    revision: int
    conversation_id: str
    sequence: int
    status: Literal["admitted", "running", "completed", "failed", "cancelled"]
    context_policy: ContextPolicyResponse
    user_message: MessageResponse
    assistant_message: MessageResponse | None
    execution_references: ExecutionReferencesResponse
    failure: TurnFailureResponse | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_domain(cls, turn: Turn) -> TurnResponse:
        return cls(
            object_type=turn.object_type,
            schema_version=turn.schema_version,
            id=turn.id,
            revision=turn.revision,
            conversation_id=turn.conversation_id,
            sequence=turn.sequence,
            status=turn.status.value,
            context_policy=ContextPolicyResponse(**turn.context_policy.model_dump()),
            user_message=MessageResponse.from_domain(turn.user_message),
            assistant_message=(
                MessageResponse.from_domain(turn.assistant_message) if turn.assistant_message is not None else None
            ),
            execution_references=ExecutionReferencesResponse(**turn.execution_references.model_dump()),
            failure=(TurnFailureResponse(**turn.failure.model_dump()) if turn.failure else None),
            created_at=turn.created_at,
            updated_at=turn.updated_at,
            completed_at=turn.completed_at,
        )


class TurnListResponse(ApiModel):
    conversation_id: str
    turns: tuple[TurnResponse, ...]


class SubmitTurnRequest(ApiModel):
    text: str = Field(min_length=1, max_length=2_500)

    @field_validator("text")
    @classmethod
    def text_is_meaningful(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text must contain a non-whitespace character.")
        return normalized


class PublicConfigResponse(ApiModel):
    debug_enabled: bool
    studio_ui_url: str | None
    service_namespace: str
    service_name: str

    @classmethod
    def from_settings(cls, settings: DebugSettings) -> PublicConfigResponse:
        return cls(
            debug_enabled=settings.enabled,
            studio_ui_url=settings.studio_ui_url,
            service_namespace=settings.service_namespace,
            service_name=settings.service_name,
        )


class TurnProblemResponse(ApiModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str
    turn_id: str | None = None
    workflow_run_id: str | None = None
    agent_run_id: str | None = None
    termination_reason: str | None = None
    turn: TurnResponse | None = None
