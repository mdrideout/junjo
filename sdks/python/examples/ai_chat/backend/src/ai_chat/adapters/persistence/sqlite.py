"""SQLite adapter for schema-versioned canonical AI Chat Turn objects."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite
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
    ContactSex,
    ContextPolicyReference,
    Conversation,
    ConversationOverview,
    HistoryMatch,
    ImageArtifact,
    MessageRole,
    Turn,
    TurnFailure,
    TurnStatus,
)
from ai_chat.domain.ports import Clock, IdFactory

_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    sex TEXT NOT NULL CHECK (sex IN ('male', 'female')),
    age INTEGER NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    bio TEXT NOT NULL,
    avatar_id TEXT NOT NULL,
    avatar_url TEXT NOT NULL,
    avatar_alt_text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    contact_id TEXT NOT NULL REFERENCES contacts(id)
);
CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    sequence INTEGER NOT NULL,
    document_json TEXT NOT NULL,
    UNIQUE(conversation_id, sequence)
);
CREATE INDEX IF NOT EXISTS turns_conversation_sequence
    ON turns(conversation_id, sequence);
"""


class SqliteChatStore:
    """Persist canonical Turn JSON with deterministic identity projections."""

    def __init__(
        self,
        *,
        path: Path,
        id_factory: IdFactory,
        clock: Clock,
        seed_demo: bool = True,
    ) -> None:
        self._path = path
        self._id_factory = id_factory
        self._clock = clock
        self._seed_demo = seed_demo

    async def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with self._connection() as database:
            await database.executescript(_SCHEMA)
            if self._seed_demo:
                await database.execute(
                    """
                    INSERT OR IGNORE INTO contacts(
                        id, first_name, last_name, sex, age, city, state, bio,
                        avatar_id, avatar_url, avatar_alt_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "demo-contact",
                        "Junjo",
                        "Guide",
                        "female",
                        31,
                        "Brooklyn",
                        "NY",
                        "A deterministic contact used by the Junjo hybrid execution example.",
                        "demo-avatar",
                        "/api/images/demo-avatar.svg",
                        "Portrait of Junjo Guide",
                    ),
                )
                await database.execute(
                    "INSERT OR IGNORE INTO conversations(id, title, contact_id) VALUES (?, ?, ?)",
                    ("demo", "Junjo Agent Demo", "demo-contact"),
                )
            await database.commit()

    async def close(self) -> None:
        return None

    async def list_conversations(self) -> tuple[ConversationOverview, ...]:
        async with self._connection() as database:
            rows = await _rows(
                database,
                """
                SELECT conversations.id, conversations.title, conversations.contact_id,
                       contacts.first_name, contacts.last_name, contacts.sex,
                       contacts.age, contacts.city, contacts.state, contacts.bio,
                       contacts.avatar_id, contacts.avatar_url, contacts.avatar_alt_text,
                       MAX(json_extract(turns.document_json, '$.updated_at')) AS last_message_at
                FROM conversations
                JOIN contacts ON contacts.id = conversations.contact_id
                LEFT JOIN turns ON turns.conversation_id = conversations.id
                GROUP BY conversations.id
                ORDER BY COALESCE(last_message_at, '') DESC, conversations.id
                """,
            )
        return tuple(
            ConversationOverview(
                conversation=Conversation(
                    id=_text(row, "id"),
                    title=_text(row, "title"),
                    contact_id=_text(row, "contact_id"),
                ),
                contact=_contact_from_row(row),
                last_message_at=row["last_message_at"],
            )
            for row in rows
        )

    async def create_contact(
        self,
        *,
        contact: ContactProfile,
        conversation: Conversation,
    ) -> ConversationOverview:
        if conversation.contact_id != contact.id:
            raise TurnPersistenceError("Conversation must reference the new contact.")
        async with self._connection() as database:
            await database.execute("BEGIN IMMEDIATE")
            try:
                await database.execute(
                    """
                    INSERT INTO contacts(
                        id, first_name, last_name, sex, age, city, state, bio,
                        avatar_id, avatar_url, avatar_alt_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        contact.id,
                        contact.first_name,
                        contact.last_name,
                        contact.sex.value,
                        contact.age,
                        contact.city,
                        contact.state,
                        contact.bio,
                        contact.avatar.id,
                        contact.avatar.url,
                        contact.avatar.alt_text,
                    ),
                )
                await database.execute(
                    "INSERT INTO conversations(id, title, contact_id) VALUES (?, ?, ?)",
                    (conversation.id, conversation.title, conversation.contact_id),
                )
                await database.commit()
            except BaseException:
                await database.rollback()
                raise
        return ConversationOverview(
            conversation=conversation,
            contact=contact,
            last_message_at=None,
        )

    async def get_contact_for_conversation(self, conversation_id: str) -> ContactProfile:
        async with self._connection() as database:
            row = await _row(
                database,
                """
                SELECT contacts.*
                FROM conversations
                JOIN contacts ON contacts.id = conversations.contact_id
                WHERE conversations.id = ?
                """,
                (conversation_id,),
            )
        if row is None:
            raise ContactNotFoundError(conversation_id)
        return _contact_from_row(row)

    async def admit_turn(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        text: str,
        context_policy: ContextPolicyReference,
    ) -> Turn:
        async with self._connection() as database:
            await database.execute("BEGIN IMMEDIATE")
            try:
                await _require_conversation(database, conversation_id)
                existing = await _rows(
                    database,
                    "SELECT document_json FROM turns WHERE conversation_id = ? ORDER BY sequence",
                    (conversation_id,),
                )
                if any(_turn_from_row(row).status in {TurnStatus.ADMITTED, TurnStatus.RUNNING} for row in existing):
                    raise TurnInProgressError(conversation_id)
                duplicate = await _row(
                    database,
                    "SELECT id FROM turns WHERE id = ?",
                    (turn_id,),
                )
                if duplicate is not None:
                    raise TurnPersistenceError(f"Turn {turn_id} already exists.")
                sequence_row = await _row(
                    database,
                    "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence FROM turns WHERE conversation_id = ?",
                    (conversation_id,),
                )
                if sequence_row is None:
                    raise TurnPersistenceError("Could not allocate a Turn sequence.")
                sequence = int(sequence_row["next_sequence"])
                now = self._clock()
                turn = Turn(
                    id=turn_id,
                    revision=0,
                    conversation_id=conversation_id,
                    sequence=sequence,
                    status=TurnStatus.ADMITTED,
                    context_policy=context_policy,
                    user_message=ChatMessage(
                        id=self._id_factory(),
                        turn_id=turn_id,
                        conversation_id=conversation_id,
                        role=MessageRole.USER,
                        content=text,
                        created_at=now,
                    ),
                    created_at=now,
                    updated_at=now,
                )
                turn = _validated_turn(turn)
                await database.execute(
                    "INSERT INTO turns(id, conversation_id, sequence, document_json) VALUES (?, ?, ?, ?)",
                    (turn.id, turn.conversation_id, turn.sequence, _turn_json(turn)),
                )
                await database.commit()
            except BaseException:
                await database.rollback()
                raise
        return turn

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
            return turn.record_outcome(
                assistant_message=ChatMessage(
                    id=self._id_factory(),
                    turn_id=turn.id,
                    conversation_id=turn.conversation_id,
                    role=MessageRole.ASSISTANT,
                    content=output.message,
                    image=output.image,
                    created_at=now,
                ),
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
        agent_run_id: str | None,
    ) -> Turn:
        if status not in {TurnStatus.FAILED, TurnStatus.CANCELLED}:
            raise ValueError("A terminal failure status must be failed or cancelled.")
        return await self._update(
            turn_id,
            lambda turn: turn.terminate(
                status=status,
                failure=failure,
                agent_run_id=agent_run_id,
                now=self._clock(),
            ),
        )

    async def get_turn(self, turn_id: str) -> Turn:
        async with self._connection() as database:
            row = await _row(
                database,
                "SELECT document_json FROM turns WHERE id = ?",
                (turn_id,),
            )
        if row is None:
            raise TurnNotFoundError(turn_id)
        return _turn_from_row(row)

    async def list_turns(self, conversation_id: str) -> tuple[Turn, ...]:
        async with self._connection() as database:
            await _require_conversation(database, conversation_id)
            rows = await _rows(
                database,
                "SELECT document_json FROM turns WHERE conversation_id = ? ORDER BY sequence",
                (conversation_id,),
            )
        return tuple(_turn_from_row(row) for row in rows)

    async def recent_completed_turns(
        self,
        conversation_id: str,
        before_sequence: int,
        limit: int,
    ) -> tuple[CompletedTurn, ...]:
        async with self._connection() as database:
            await _require_conversation(database, conversation_id)
            rows = await _rows(
                database,
                """
                SELECT document_json FROM turns
                WHERE conversation_id = ? AND sequence < ?
                ORDER BY sequence
                """,
                (conversation_id, before_sequence),
            )
        completed = [turn for turn in (_turn_from_row(row) for row in rows) if turn.status is TurnStatus.COMPLETED][
            -limit:
        ]
        return tuple(_completed_turn(turn) for turn in completed)

    async def search_history(
        self,
        conversation_id: str,
        before_sequence: int,
        query: str,
        limit: int,
    ) -> tuple[HistoryMatch, ...]:
        async with self._connection() as database:
            await _require_conversation(database, conversation_id)
            rows = await _rows(
                database,
                """
                SELECT document_json FROM turns
                WHERE conversation_id = ? AND sequence < ?
                ORDER BY sequence
                """,
                (conversation_id, before_sequence),
            )
        needle = query.casefold()
        matches: list[HistoryMatch] = []
        for row in rows:
            turn = _turn_from_row(row)
            if turn.status is not TurnStatus.COMPLETED:
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
        async with self._connection() as database:
            await database.execute("BEGIN IMMEDIATE")
            try:
                row = await _row(
                    database,
                    "SELECT document_json FROM turns WHERE id = ?",
                    (turn_id,),
                )
                if row is None:
                    raise TurnNotFoundError(turn_id)
                current = _turn_from_row(row)
                updated = transition(current)
                if (
                    updated.id != current.id
                    or updated.conversation_id != current.conversation_id
                    or updated.sequence != current.sequence
                ):
                    raise TurnPersistenceError("A Turn transition cannot change aggregate identity.")
                if updated.revision != current.revision + 1:
                    raise TurnPersistenceError("A Turn transition must advance exactly one revision.")
                updated = _validated_turn(updated)
                await database.execute(
                    "UPDATE turns SET document_json = ? WHERE id = ?",
                    (_turn_json(updated), turn_id),
                )
                await database.commit()
            except BaseException:
                await database.rollback()
                raise
        return updated

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[aiosqlite.Connection]:
        database = await aiosqlite.connect(self._path)
        database.row_factory = aiosqlite.Row
        await database.execute("PRAGMA foreign_keys = ON")
        try:
            yield database
        finally:
            await database.close()


def _turn_json(turn: Turn) -> str:
    return turn.model_dump_json()


def _validated_turn(turn: Turn) -> Turn:
    try:
        return Turn.model_validate_json(turn.model_dump_json())
    except ValidationError as error:
        raise TurnPersistenceError("Turn document violates schema version 1.") from error


def _turn_from_row(row: aiosqlite.Row) -> Turn:
    raw = row["document_json"]
    if not isinstance(raw, str):
        raise TurnPersistenceError("Stored Turn document is not JSON text.")
    try:
        return Turn.model_validate_json(raw)
    except ValidationError as error:
        raise TurnPersistenceError("Stored Turn document violates schema version 1.") from error


def _completed_turn(turn: Turn) -> CompletedTurn:
    if turn.assistant_message is None:
        raise TurnPersistenceError(f"Completed Turn {turn.id} has no assistant message.")
    return CompletedTurn(user=turn.user_message, assistant=turn.assistant_message)


async def _require_conversation(database: aiosqlite.Connection, conversation_id: str) -> None:
    row = await _row(database, "SELECT id FROM conversations WHERE id = ?", (conversation_id,))
    if row is None:
        raise ConversationNotFoundError(conversation_id)


async def _row(
    database: aiosqlite.Connection,
    query: str,
    parameters: tuple[object, ...] = (),
) -> aiosqlite.Row | None:
    cursor = await database.execute(query, parameters)
    return await cursor.fetchone()


async def _rows(
    database: aiosqlite.Connection,
    query: str,
    parameters: tuple[object, ...] = (),
) -> list[aiosqlite.Row]:
    cursor = await database.execute(query, parameters)
    return list(await cursor.fetchall())


def _text(row: aiosqlite.Row, name: str) -> str:
    value: Any = row[name]
    if not isinstance(value, str):
        raise TurnPersistenceError(f"Expected text column {name}.")
    return value


def _contact_from_row(row: aiosqlite.Row) -> ContactProfile:
    try:
        age = int(row["age"])
    except (TypeError, ValueError) as error:
        raise TurnPersistenceError("Expected integer column age.") from error
    return ContactProfile(
        id=_text(row, "contact_id") if "contact_id" in row.keys() else _text(row, "id"),
        first_name=_text(row, "first_name"),
        last_name=_text(row, "last_name"),
        sex=ContactSex(_text(row, "sex")),
        age=age,
        city=_text(row, "city"),
        state=_text(row, "state"),
        bio=_text(row, "bio"),
        avatar=ImageArtifact(
            id=_text(row, "avatar_id"),
            url=_text(row, "avatar_url"),
            alt_text=_text(row, "avatar_alt_text"),
        ),
    )
