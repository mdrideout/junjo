"""Deterministic lock-protected persistence for tests and examples."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from pydantic import ValidationError

from ai_chat.domain.errors import (
    ContactNotFoundError,
    ConversationNotFoundError,
    TurnInProgressError,
    TurnNotFoundError,
    TurnPersistenceError,
)
from ai_chat.domain.models import (
    ChatAgentOutput,
    ChatMessage,
    CompletedTurn,
    ContactProfile,
    ContextPolicyReference,
    Conversation,
    ConversationOverview,
    HistoryMatch,
    MessageRole,
    Turn,
    TurnFailure,
    TurnStatus,
)
from ai_chat.domain.ports import Clock, IdFactory


class InMemoryChatStore:
    """One application aggregate implementing narrow persistence ports."""

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
        self._turns: list[Turn] = []
        self._id_factory = id_factory
        self._clock = clock
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._lock:
            if not any(
                turn.status in {TurnStatus.ADMITTED, TurnStatus.RUNNING}
                for turn in self._turns
            ):
                return
            now = self._clock()
            self._turns = [
                _validated_turn(turn.interrupt(now=now))
                if turn.status in {TurnStatus.ADMITTED, TurnStatus.RUNNING}
                else turn
                for turn in self._turns
            ]

    async def close(self) -> None:
        return None

    async def list_conversations(self) -> tuple[ConversationOverview, ...]:
        async with self._lock:
            return tuple(
                self._overview(item).model_copy(deep=True)
                for item in sorted(self._conversations.values(), key=lambda value: value.id)
            )

    async def create_contact(
        self,
        *,
        contact: ContactProfile,
        conversation: Conversation,
    ) -> ConversationOverview:
        async with self._lock:
            if contact.id in self._contacts or conversation.id in self._conversations:
                raise TurnPersistenceError("Contact or conversation identity already exists.")
            if conversation.contact_id != contact.id:
                raise TurnPersistenceError("Conversation must reference the new contact.")
            self._contacts[contact.id] = contact.model_copy(deep=True)
            self._conversations[conversation.id] = conversation.model_copy(deep=True)
            return self._overview(conversation).model_copy(deep=True)

    async def get_contact_for_conversation(self, conversation_id: str) -> ContactProfile:
        async with self._lock:
            conversation = self._conversation(conversation_id)
            contact = self._contacts.get(conversation.contact_id)
            if contact is None:
                raise ContactNotFoundError(conversation_id)
            return contact.model_copy(deep=True)

    async def admit_turn(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        text: str,
        context_policy: ContextPolicyReference,
    ) -> Turn:
        async with self._lock:
            self._conversation(conversation_id)
            if any(
                item.conversation_id == conversation_id and item.status in {TurnStatus.ADMITTED, TurnStatus.RUNNING}
                for item in self._turns
            ):
                raise TurnInProgressError(conversation_id)
            if any(item.id == turn_id for item in self._turns):
                raise TurnPersistenceError(f"Turn {turn_id} already exists.")
            sequence = 1 + max(
                (item.sequence for item in self._turns if item.conversation_id == conversation_id),
                default=0,
            )
            now = self._clock()
            user_message = ChatMessage(
                id=self._id_factory(),
                turn_id=turn_id,
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=text,
                created_at=now,
            )
            turn = Turn(
                id=turn_id,
                revision=0,
                conversation_id=conversation_id,
                sequence=sequence,
                status=TurnStatus.ADMITTED,
                context_policy=context_policy,
                user_message=user_message,
                created_at=now,
                updated_at=now,
            )
            validated = _validated_turn(turn)
            self._turns.append(validated)
            return validated.model_copy(deep=True)

    async def start_turn(self, turn_id: str) -> Turn:
        return await self._update(turn_id, lambda turn: turn.start(self._clock()))

    async def record_turn_outcome(
        self,
        *,
        turn_id: str,
        output: ChatAgentOutput,
        agent_run_id: str | None,
    ) -> Turn:
        def transition(turn: Turn) -> Turn:
            now = self._clock()
            assistant_message = ChatMessage(
                id=self._id_factory(),
                turn_id=turn.id,
                conversation_id=turn.conversation_id,
                role=MessageRole.ASSISTANT,
                content=output.message,
                image=output.image,
                created_at=now,
            )
            return turn.record_outcome(
                assistant_message=assistant_message,
                agent_run_id=agent_run_id,
                now=now,
            )

        return await self._update(turn_id, transition)

    async def complete_turn(self, *, turn_id: str, workflow_run_id: str) -> Turn:
        return await self._update(
            turn_id,
            lambda turn: turn.complete(workflow_run_id=workflow_run_id, now=self._clock()),
        )

    async def terminate_turn(
        self,
        *,
        turn_id: str,
        status: TurnStatus,
        failure: TurnFailure,
        workflow_run_id: str | None,
        agent_run_id: str | None,
    ) -> Turn:
        if status not in {TurnStatus.FAILED, TurnStatus.CANCELLED}:
            raise ValueError("A terminal failure status must be failed or cancelled.")
        return await self._update(
            turn_id,
            lambda turn: turn.terminate(
                status=status,
                failure=failure,
                workflow_run_id=workflow_run_id,
                agent_run_id=agent_run_id,
                now=self._clock(),
            ),
        )

    async def get_turn(self, turn_id: str) -> Turn:
        async with self._lock:
            return self._turn(turn_id).model_copy(deep=True)

    async def list_turns(self, conversation_id: str) -> tuple[Turn, ...]:
        async with self._lock:
            self._conversation(conversation_id)
            return tuple(item.model_copy(deep=True) for item in self._turns if item.conversation_id == conversation_id)

    async def recent_completed_turns(
        self,
        conversation_id: str,
        before_sequence: int,
        limit: int,
    ) -> tuple[CompletedTurn, ...]:
        async with self._lock:
            self._conversation(conversation_id)
            eligible = [
                item
                for item in self._turns
                if item.conversation_id == conversation_id
                and item.sequence < before_sequence
                and item.status is TurnStatus.COMPLETED
            ][-limit:]
            return tuple(_completed_turn(item) for item in eligible)

    async def search_history(
        self,
        conversation_id: str,
        before_sequence: int,
        query: str,
        limit: int,
    ) -> tuple[HistoryMatch, ...]:
        async with self._lock:
            self._conversation(conversation_id)
            needle = query.casefold()
            matches: list[HistoryMatch] = []
            for turn in self._turns:
                if (
                    turn.conversation_id != conversation_id
                    or turn.sequence >= before_sequence
                    or turn.status is not TurnStatus.COMPLETED
                ):
                    continue
                for message in (turn.user_message, turn.assistant_message):
                    if message is not None and needle in message.content.casefold():
                        matches.append(
                            HistoryMatch(
                                turn_id=turn.id,
                                role=message.role,
                                content=message.content,
                            )
                        )
            return tuple(matches[-limit:])

    async def _update(self, turn_id: str, transition: Callable[[Turn], Turn]) -> Turn:
        async with self._lock:
            for index, current in enumerate(self._turns):
                if current.id != turn_id:
                    continue
                updated = transition(current)
                if (
                    updated.id != current.id
                    or updated.conversation_id != current.conversation_id
                    or updated.sequence != current.sequence
                ):
                    raise TurnPersistenceError("A Turn transition cannot change aggregate identity.")
                if updated.revision != current.revision + 1:
                    raise TurnPersistenceError("A Turn transition must advance exactly one revision.")
                validated = _validated_turn(updated)
                self._turns[index] = validated
                return validated.model_copy(deep=True)
        raise TurnNotFoundError(turn_id)

    def _conversation(self, conversation_id: str) -> Conversation:
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        return conversation

    def _turn(self, turn_id: str) -> Turn:
        for turn in self._turns:
            if turn.id == turn_id:
                return turn
        raise TurnNotFoundError(turn_id)

    def _overview(self, conversation: Conversation) -> ConversationOverview:
        contact = self._contacts.get(conversation.contact_id)
        if contact is None:
            raise ContactNotFoundError(conversation.id)
        latest = max(
            (turn.updated_at for turn in self._turns if turn.conversation_id == conversation.id),
            default=None,
        )
        return ConversationOverview(
            conversation=conversation,
            contact=contact,
            last_message_at=latest,
        )


def _completed_turn(turn: Turn) -> CompletedTurn:
    if turn.assistant_message is None:
        raise TurnPersistenceError(f"Completed Turn {turn.id} has no assistant message.")
    return CompletedTurn(user=turn.user_message, assistant=turn.assistant_message)


def _validated_turn(turn: Turn) -> Turn:
    try:
        return Turn.model_validate_json(turn.model_dump_json())
    except ValidationError as error:
        raise TurnPersistenceError("Turn document violates schema version 1.") from error
