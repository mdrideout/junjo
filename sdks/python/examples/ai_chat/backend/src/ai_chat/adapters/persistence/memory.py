"""Deterministic in-memory persistence for tests and examples."""

from __future__ import annotations

import asyncio

from ai_chat.domain.errors import ContactNotFoundError, ConversationNotFoundError, TurnPersistenceError
from ai_chat.domain.models import (
    ChatAgentOutput,
    ChatMessage,
    CompletedTurn,
    ContactProfile,
    Conversation,
    HistoryMatch,
    MessageRole,
)
from ai_chat.domain.ports import Clock, IdFactory


class InMemoryChatStore:
    """One lock-protected aggregate implementing the narrow persistence ports."""

    def __init__(
        self,
        *,
        conversations: tuple[Conversation, ...],
        contacts: tuple[ContactProfile, ...],
        id_factory: IdFactory,
        clock: Clock,
    ) -> None:
        self._conversations = {item.id: item for item in conversations}
        self._contacts = {item.id: item for item in contacts}
        self._messages: list[ChatMessage] = []
        self._id_factory = id_factory
        self._clock = clock
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def list_conversations(self) -> tuple[Conversation, ...]:
        async with self._lock:
            return tuple(
                item.model_copy(deep=True) for item in sorted(self._conversations.values(), key=lambda value: value.id)
            )

    async def get_contact_for_conversation(self, conversation_id: str) -> ContactProfile:
        async with self._lock:
            conversation = self._conversation(conversation_id)
            contact = self._contacts.get(conversation.contact_id)
            if contact is None:
                raise ContactNotFoundError(conversation_id)
            return contact.model_copy(deep=True)

    async def append_user_message(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        content: str,
    ) -> ChatMessage:
        async with self._lock:
            self._conversation(conversation_id)
            self._assert_role_available(turn_id, MessageRole.USER)
            message = ChatMessage(
                id=self._id_factory(),
                turn_id=turn_id,
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=content,
                created_at=self._clock(),
            )
            self._messages.append(message)
            return message.model_copy(deep=True)

    async def append_assistant_message(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        output: ChatAgentOutput,
    ) -> ChatMessage:
        async with self._lock:
            self._conversation(conversation_id)
            if not any(message.turn_id == turn_id and message.role == MessageRole.USER for message in self._messages):
                raise TurnPersistenceError("An assistant message requires its persisted user input.")
            self._assert_role_available(turn_id, MessageRole.ASSISTANT)
            message = ChatMessage(
                id=self._id_factory(),
                turn_id=turn_id,
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=output.message,
                image=output.image,
                created_at=self._clock(),
            )
            self._messages.append(message)
            return message.model_copy(deep=True)

    async def list_messages(self, conversation_id: str) -> tuple[ChatMessage, ...]:
        async with self._lock:
            self._conversation(conversation_id)
            return tuple(
                item.model_copy(deep=True) for item in self._messages if item.conversation_id == conversation_id
            )

    async def completed_turns_before(
        self,
        conversation_id: str,
        before_turn_id: str,
    ) -> tuple[CompletedTurn, ...]:
        async with self._lock:
            self._conversation(conversation_id)
            prior = self._prior_messages(conversation_id, before_turn_id)
            return _complete_turns(prior)

    async def search_history(
        self,
        conversation_id: str,
        before_turn_id: str,
        query: str,
        limit: int,
    ) -> tuple[HistoryMatch, ...]:
        async with self._lock:
            self._conversation(conversation_id)
            needle = query.casefold()
            matches = [
                HistoryMatch(turn_id=item.turn_id, role=item.role, content=item.content)
                for item in self._prior_messages(conversation_id, before_turn_id)
                if needle in item.content.casefold()
            ]
            return tuple(matches[-limit:])

    def _conversation(self, conversation_id: str) -> Conversation:
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        return conversation

    def _assert_role_available(self, turn_id: str, role: MessageRole) -> None:
        if any(item.turn_id == turn_id and item.role == role for item in self._messages):
            raise TurnPersistenceError(f"Turn {turn_id} already has a {role.value} message.")

    def _prior_messages(self, conversation_id: str, before_turn_id: str) -> list[ChatMessage]:
        for index, item in enumerate(self._messages):
            if item.conversation_id == conversation_id and item.turn_id == before_turn_id:
                return [message for message in self._messages[:index] if message.conversation_id == conversation_id]
        raise TurnPersistenceError(f"Current turn {before_turn_id} has no persisted input.")


def _complete_turns(messages: list[ChatMessage]) -> tuple[CompletedTurn, ...]:
    ordered_ids: list[str] = []
    grouped: dict[str, dict[MessageRole, ChatMessage]] = {}
    for message in messages:
        if message.turn_id not in grouped:
            ordered_ids.append(message.turn_id)
            grouped[message.turn_id] = {}
        grouped[message.turn_id][message.role] = message
    turns: list[CompletedTurn] = []
    for turn_id in ordered_ids:
        pair = grouped[turn_id]
        user = pair.get(MessageRole.USER)
        assistant = pair.get(MessageRole.ASSISTANT)
        if user is not None and assistant is not None:
            turns.append(CompletedTurn(user=user, assistant=assistant))
    return tuple(turns)
