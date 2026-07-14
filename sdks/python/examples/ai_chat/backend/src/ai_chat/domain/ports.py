"""Narrow application capability contracts implemented by adapters."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from .models import (
    ChatAgentOutput,
    ChatMessage,
    CompletedTurn,
    ContactProfile,
    Conversation,
    HistoryMatch,
    ImageArtifact,
)

IdFactory = Callable[[], str]
Clock = Callable[[], datetime]


class ConversationReader(Protocol):
    async def list_conversations(self) -> tuple[Conversation, ...]: ...


class ContactReader(Protocol):
    async def get_contact_for_conversation(self, conversation_id: str) -> ContactProfile: ...


class HistoryReader(Protocol):
    async def completed_turns_before(
        self,
        conversation_id: str,
        before_turn_id: str,
    ) -> tuple[CompletedTurn, ...]: ...

    async def search_history(
        self,
        conversation_id: str,
        before_turn_id: str,
        query: str,
        limit: int,
    ) -> tuple[HistoryMatch, ...]: ...


class MessageRepository(Protocol):
    async def append_user_message(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        content: str,
    ) -> ChatMessage: ...

    async def append_assistant_message(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        output: ChatAgentOutput,
    ) -> ChatMessage: ...

    async def list_messages(self, conversation_id: str) -> tuple[ChatMessage, ...]: ...


class ImageRenderer(Protocol):
    async def render(self, *, prompt: str, alt_text: str) -> ImageArtifact: ...


class ApplicationStore(
    ConversationReader,
    ContactReader,
    HistoryReader,
    MessageRepository,
    Protocol,
):
    async def initialize(self) -> None: ...

    async def close(self) -> None: ...
