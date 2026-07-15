"""Portable typed values owned by the chat application."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DomainModel(BaseModel):
    """Immutable base for values crossing application boundaries."""

    model_config = ConfigDict(frozen=True)


class MessageRole(StrEnum):
    """The two persisted roles used by this bounded chat example."""

    USER = "user"
    ASSISTANT = "assistant"


class TurnStatus(StrEnum):
    """Durable lifecycle of one server-admitted conversation turn."""

    ADMITTED = "admitted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ContactSex(StrEnum):
    MALE = "male"
    FEMALE = "female"


class MessageDirective(StrEnum):
    """Known deterministic branches in the restored message Workflow."""

    GENERAL_RESPONSE = "general_response"
    WORK_RELATED_RESPONSE = "work_related_response"
    DATE_IDEA_RESEARCH = "date_idea_research"
    IMAGE_RESPONSE = "image_response"


class Conversation(DomainModel):
    object_type: Literal["ai_chat.conversation"] = "ai_chat.conversation"
    schema_version: Literal[1] = 1
    id: str
    title: str
    contact_id: str


class ImageArtifact(DomainModel):
    id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    alt_text: str = Field(min_length=1)


class ImageEditResult(DomainModel):
    """Image artifact and optional provider-authored accompanying text."""

    artifact: ImageArtifact
    text: str | None = None


class PersonalityTraits(DomainModel):
    """Normalized traits used to create and preserve one contact persona."""

    openness: float = Field(ge=0.0, le=1.0)
    conscientiousness: float = Field(ge=0.0, le=1.0)
    extraversion: float = Field(ge=0.0, le=1.0)
    agreeableness: float = Field(ge=0.0, le=1.0)
    neuroticism: float = Field(ge=0.0, le=1.0)
    intelligence: float = Field(ge=0.0, le=1.0)
    religiousness: float = Field(ge=0.0, le=1.0)
    attractiveness: float = Field(ge=0.0, le=1.0)
    trauma: float = Field(ge=0.0, le=1.0)


class ContactProfile(DomainModel):
    object_type: Literal["ai_chat.contact"] = "ai_chat.contact"
    schema_version: Literal[1] = 1
    id: str
    first_name: str
    last_name: str
    sex: ContactSex
    age: int = Field(ge=18, le=100)
    personality: PersonalityTraits
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    city: str
    state: str
    bio: str
    avatar: ImageArtifact

    @property
    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class ConversationOverview(DomainModel):
    conversation: Conversation
    contact: ContactProfile
    last_message_at: datetime | None = None


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


class ContextPolicyReference(DomainModel):
    """Exact bounded context policy used for one Turn execution."""

    id: Literal["recent-completed-turns"] = "recent-completed-turns"
    version: Literal[1] = 1
    recent_turn_limit: int = Field(default=8, ge=1, le=50)


class ExecutionReferences(DomainModel):
    """Durable semantic locators for Studio execution evidence."""

    workflow_run_id: str | None = None
    agent_run_id: str | None = None


class TurnFailure(DomainModel):
    """Safe application failure recorded with a terminal Turn."""

    code: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    termination_reason: str | None = None


class Turn(DomainModel):
    """Versioned canonical product record for one accepted user action."""

    object_type: Literal["ai_chat.turn"] = "ai_chat.turn"
    schema_version: Literal[1] = 1
    id: str = Field(min_length=1)
    revision: int = Field(ge=0)
    conversation_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    status: TurnStatus
    context_policy: ContextPolicyReference
    user_message: ChatMessage
    assistant_message: ChatMessage | None = None
    execution_references: ExecutionReferences = Field(default_factory=ExecutionReferences)
    failure: TurnFailure | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def message_identity_is_coherent(self) -> Turn:
        if self.user_message.role is not MessageRole.USER:
            raise ValueError("Turn user_message must have the user role.")
        if self.user_message.turn_id != self.id:
            raise ValueError("Turn user_message must reference the owning Turn.")
        if self.user_message.conversation_id != self.conversation_id:
            raise ValueError("Turn user_message must reference the owning conversation.")
        if self.assistant_message is not None:
            if self.assistant_message.role is not MessageRole.ASSISTANT:
                raise ValueError("Turn assistant_message must have the assistant role.")
            if self.assistant_message.turn_id != self.id:
                raise ValueError("Turn assistant_message must reference the owning Turn.")
            if self.assistant_message.conversation_id != self.conversation_id:
                raise ValueError("Turn assistant_message must reference the owning conversation.")

        return self

    @model_validator(mode="after")
    def terminal_lifecycle_is_coherent(self) -> Turn:
        if self.status is TurnStatus.COMPLETED:
            if self.assistant_message is None:
                raise ValueError("A completed Turn requires an assistant message.")
            if self.execution_references.workflow_run_id is None:
                raise ValueError("A completed Turn requires a Workflow run reference.")
            if self.completed_at is None:
                raise ValueError("A completed Turn requires completed_at.")
            if self.failure is not None:
                raise ValueError("A completed Turn cannot contain failure evidence.")
        elif self.status in {TurnStatus.FAILED, TurnStatus.CANCELLED}:
            if self.failure is None or self.completed_at is None:
                raise ValueError("A failed or cancelled Turn requires terminal failure evidence.")
        elif self.failure is not None or self.completed_at is not None:
            raise ValueError("A non-terminal Turn cannot contain terminal evidence.")
        return self

    def start(self, now: datetime) -> Turn:
        if self.status is not TurnStatus.ADMITTED:
            raise ValueError("Only an admitted Turn can start.")
        return self.model_copy(
            update={
                "revision": self.revision + 1,
                "status": TurnStatus.RUNNING,
                "updated_at": now,
            }
        )

    def record_outcome(
        self,
        *,
        assistant_message: ChatMessage,
        agent_run_id: str | None,
        now: datetime,
    ) -> Turn:
        if self.status is not TurnStatus.RUNNING:
            raise ValueError("Only a running Turn can record an Agent outcome.")
        return self.model_copy(
            update={
                "revision": self.revision + 1,
                "assistant_message": assistant_message,
                "execution_references": self.execution_references.model_copy(update={"agent_run_id": agent_run_id}),
                "updated_at": now,
            }
        )

    def complete(self, *, workflow_run_id: str, now: datetime) -> Turn:
        if self.status is not TurnStatus.RUNNING or self.assistant_message is None:
            raise ValueError("Only a running Turn with an Agent outcome can complete.")
        return self.model_copy(
            update={
                "revision": self.revision + 1,
                "status": TurnStatus.COMPLETED,
                "execution_references": self.execution_references.model_copy(
                    update={"workflow_run_id": workflow_run_id}
                ),
                "updated_at": now,
                "completed_at": now,
            }
        )

    def terminate(
        self,
        *,
        status: Literal[TurnStatus.FAILED, TurnStatus.CANCELLED],
        failure: TurnFailure,
        workflow_run_id: str | None,
        agent_run_id: str | None,
        now: datetime,
    ) -> Turn:
        if self.status not in {TurnStatus.ADMITTED, TurnStatus.RUNNING}:
            raise ValueError("Only an active Turn can terminate.")
        references = self.execution_references
        references = references.model_copy(
            update={
                "workflow_run_id": workflow_run_id or references.workflow_run_id,
                "agent_run_id": agent_run_id or references.agent_run_id,
            }
        )
        return self.model_copy(
            update={
                "revision": self.revision + 1,
                "status": status,
                "execution_references": references,
                "failure": failure,
                "updated_at": now,
                "completed_at": now,
            }
        )

    def interrupt(self, *, now: datetime) -> Turn:
        """Reconcile an active Turn abandoned by an earlier process."""

        return self.terminate(
            status=TurnStatus.FAILED,
            failure=TurnFailure(
                code="turn_interrupted",
                detail="Turn execution was interrupted before it reached a terminal state.",
                termination_reason="process_interrupted",
            ),
            workflow_run_id=None,
            agent_run_id=None,
            now=now,
        )


class ChatAgentInput(DomainModel):
    conversation_id: str
    turn_id: str
    contact: ContactProfile
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


class CreateImageInput(DomainModel):
    prompt: str = Field(min_length=1, max_length=500)


class CreateImageOutput(DomainModel):
    artifact: ImageArtifact
