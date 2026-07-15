"""Narrow application capability contracts implemented by adapters."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol, TypeVar

from pydantic import BaseModel

from .models import (
    ChatAgentOutput,
    CompletedTurn,
    ContactProfile,
    ContextPolicyReference,
    Conversation,
    ConversationOverview,
    HistoryMatch,
    ImageArtifact,
    ImageEditResult,
    Turn,
    TurnFailure,
    TurnStatus,
)

IdFactory = Callable[[], str]
Clock = Callable[[], datetime]
StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class ConversationReader(Protocol):
    async def list_conversations(self) -> tuple[ConversationOverview, ...]: ...


class ContactWriter(Protocol):
    async def create_contact(
        self,
        *,
        contact: ContactProfile,
        conversation: Conversation,
    ) -> ConversationOverview: ...


class ContactReader(Protocol):
    async def get_contact_for_conversation(self, conversation_id: str) -> ContactProfile: ...


class HistoryReader(Protocol):
    async def recent_completed_turns(
        self,
        conversation_id: str,
        before_sequence: int,
        limit: int,
    ) -> tuple[CompletedTurn, ...]: ...

    async def search_history(
        self,
        conversation_id: str,
        before_sequence: int,
        query: str,
        limit: int,
    ) -> tuple[HistoryMatch, ...]: ...


class TurnRepository(Protocol):
    async def admit_turn(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        text: str,
        context_policy: ContextPolicyReference,
    ) -> Turn: ...

    async def start_turn(self, turn_id: str) -> Turn: ...

    async def record_turn_outcome(
        self,
        *,
        turn_id: str,
        output: ChatAgentOutput,
        agent_run_id: str | None,
    ) -> Turn: ...

    async def complete_turn(self, *, turn_id: str, workflow_run_id: str) -> Turn: ...

    async def terminate_turn(
        self,
        *,
        turn_id: str,
        status: TurnStatus,
        failure: TurnFailure,
        workflow_run_id: str | None,
        agent_run_id: str | None,
    ) -> Turn: ...

    async def get_turn(self, turn_id: str) -> Turn: ...

    async def list_turns(self, conversation_id: str) -> tuple[Turn, ...]: ...


class LanguageModel(Protocol):
    """Bounded text capabilities used by application Workflow Nodes."""

    async def generate_text(self, *, prompt: str) -> str: ...

    async def generate_structured(
        self,
        *,
        prompt: str,
        output_type: type[StructuredOutput],
    ) -> StructuredOutput: ...


class ImageModel(Protocol):
    """Application image generation and avatar-conditioned editing capability."""

    async def generate(self, *, prompt: str, alt_text: str) -> ImageArtifact: ...

    async def edit(
        self,
        *,
        source: ImageArtifact,
        prompt: str,
        alt_text: str,
    ) -> ImageEditResult: ...


class ApplicationStore(
    ConversationReader,
    ContactReader,
    ContactWriter,
    HistoryReader,
    TurnRepository,
    Protocol,
):
    async def initialize(self) -> None: ...

    async def close(self) -> None: ...
