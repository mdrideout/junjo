"""Small explicit SQLite adapter for the runnable chat application."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import aiosqlite

from ai_chat.domain.errors import ContactNotFoundError, ConversationNotFoundError, TurnPersistenceError
from ai_chat.domain.models import (
    ChatAgentOutput,
    ChatMessage,
    CompletedTurn,
    ContactProfile,
    Conversation,
    HistoryMatch,
    ImageArtifact,
    MessageRole,
)
from ai_chat.domain.ports import Clock, IdFactory

_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    bio TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    contact_id TEXT NOT NULL REFERENCES contacts(id)
);
CREATE TABLE IF NOT EXISTS messages (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    turn_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    image_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(turn_id, role)
);
"""


class SqliteChatStore:
    """SQLite implementation of all persistence ports for this one aggregate."""

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
                    "INSERT OR IGNORE INTO contacts(id, display_name, bio) VALUES (?, ?, ?)",
                    (
                        "demo-contact",
                        "Junjo Guide",
                        "A deterministic contact used by the Junjo hybrid execution example.",
                    ),
                )
                await database.execute(
                    "INSERT OR IGNORE INTO conversations(id, title, contact_id) VALUES (?, ?, ?)",
                    ("demo", "Junjo Agent Demo", "demo-contact"),
                )
            await database.commit()

    async def close(self) -> None:
        return None

    async def list_conversations(self) -> tuple[Conversation, ...]:
        async with self._connection() as database:
            rows = await _rows(
                database,
                "SELECT id, title, contact_id FROM conversations ORDER BY id",
            )
        return tuple(
            Conversation(
                id=_text(row, "id"),
                title=_text(row, "title"),
                contact_id=_text(row, "contact_id"),
            )
            for row in rows
        )

    async def get_contact_for_conversation(self, conversation_id: str) -> ContactProfile:
        async with self._connection() as database:
            row = await _row(
                database,
                """
                SELECT contacts.id, contacts.display_name, contacts.bio
                FROM conversations
                JOIN contacts ON contacts.id = conversations.contact_id
                WHERE conversations.id = ?
                """,
                (conversation_id,),
            )
        if row is None:
            raise ContactNotFoundError(conversation_id)
        return ContactProfile(
            id=_text(row, "id"),
            display_name=_text(row, "display_name"),
            bio=_text(row, "bio"),
        )

    async def append_user_message(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        content: str,
    ) -> ChatMessage:
        return await self._append_message(
            conversation_id=conversation_id,
            turn_id=turn_id,
            role=MessageRole.USER,
            content=content,
            image=None,
        )

    async def append_assistant_message(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        output: ChatAgentOutput,
    ) -> ChatMessage:
        async with self._connection() as database:
            user = await _row(
                database,
                """
                SELECT id FROM messages
                WHERE conversation_id = ? AND turn_id = ? AND role = 'user'
                """,
                (conversation_id, turn_id),
            )
        if user is None:
            raise TurnPersistenceError("An assistant message requires its persisted user input.")
        return await self._append_message(
            conversation_id=conversation_id,
            turn_id=turn_id,
            role=MessageRole.ASSISTANT,
            content=output.message,
            image=output.image,
        )

    async def list_messages(self, conversation_id: str) -> tuple[ChatMessage, ...]:
        async with self._connection() as database:
            await _require_conversation(database, conversation_id)
            rows = await _rows(
                database,
                """
                SELECT id, turn_id, conversation_id, role, content, image_json, created_at
                FROM messages WHERE conversation_id = ? ORDER BY sequence
                """,
                (conversation_id,),
            )
        return tuple(_message(row) for row in rows)

    async def completed_turns_before(
        self,
        conversation_id: str,
        before_turn_id: str,
    ) -> tuple[CompletedTurn, ...]:
        async with self._connection() as database:
            boundary = await _turn_boundary(database, conversation_id, before_turn_id)
            rows = await _rows(
                database,
                """
                SELECT id, turn_id, conversation_id, role, content, image_json, created_at
                FROM messages
                WHERE conversation_id = ? AND sequence < ?
                ORDER BY sequence
                """,
                (conversation_id, boundary),
            )
        return _complete_turns(tuple(_message(row) for row in rows))

    async def search_history(
        self,
        conversation_id: str,
        before_turn_id: str,
        query: str,
        limit: int,
    ) -> tuple[HistoryMatch, ...]:
        async with self._connection() as database:
            boundary = await _turn_boundary(database, conversation_id, before_turn_id)
            rows = await _rows(
                database,
                """
                SELECT turn_id, role, content
                FROM messages
                WHERE conversation_id = ?
                  AND sequence < ?
                  AND instr(lower(content), lower(?)) > 0
                ORDER BY sequence DESC
                LIMIT ?
                """,
                (conversation_id, boundary, query, limit),
            )
        return tuple(
            HistoryMatch(
                turn_id=_text(row, "turn_id"),
                role=MessageRole(_text(row, "role")),
                content=_text(row, "content"),
            )
            for row in reversed(rows)
        )

    async def _append_message(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        role: MessageRole,
        content: str,
        image: ImageArtifact | None,
    ) -> ChatMessage:
        message = ChatMessage(
            id=self._id_factory(),
            turn_id=turn_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            image=image,
            created_at=self._clock(),
        )
        async with self._connection() as database:
            await _require_conversation(database, conversation_id)
            try:
                await database.execute(
                    """
                    INSERT INTO messages(
                        id, turn_id, conversation_id, role, content, image_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message.id,
                        message.turn_id,
                        message.conversation_id,
                        message.role.value,
                        message.content,
                        message.image.model_dump_json() if message.image is not None else None,
                        message.created_at.isoformat(),
                    ),
                )
                await database.commit()
            except aiosqlite.IntegrityError as exc:
                raise TurnPersistenceError(f"Turn {turn_id} already has a {role.value} message.") from exc
        return message

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[aiosqlite.Connection]:
        connection = await aiosqlite.connect(self._path)
        connection.row_factory = aiosqlite.Row
        try:
            yield connection
        finally:
            await connection.close()


async def _require_conversation(database: aiosqlite.Connection, conversation_id: str) -> None:
    if await _row(database, "SELECT id FROM conversations WHERE id = ?", (conversation_id,)) is None:
        raise ConversationNotFoundError(conversation_id)


async def _turn_boundary(
    database: aiosqlite.Connection,
    conversation_id: str,
    turn_id: str,
) -> int:
    row = await _row(
        database,
        "SELECT min(sequence) AS sequence FROM messages WHERE conversation_id = ? AND turn_id = ?",
        (conversation_id, turn_id),
    )
    if row is None or row["sequence"] is None:
        raise TurnPersistenceError(f"Current turn {turn_id} has no persisted input.")
    value = row["sequence"]
    if not isinstance(value, int):
        raise TurnPersistenceError("SQLite returned a non-integer message sequence.")
    return value


async def _row(
    database: aiosqlite.Connection,
    statement: str,
    parameters: Sequence[object] = (),
) -> aiosqlite.Row | None:
    cursor = await database.execute(statement, parameters)
    return await cursor.fetchone()


async def _rows(
    database: aiosqlite.Connection,
    statement: str,
    parameters: Sequence[object] = (),
) -> list[aiosqlite.Row]:
    cursor = await database.execute(statement, parameters)
    return list(await cursor.fetchall())


def _message(row: aiosqlite.Row) -> ChatMessage:
    image_json = _optional_text(row, "image_json")
    return ChatMessage(
        id=_text(row, "id"),
        turn_id=_text(row, "turn_id"),
        conversation_id=_text(row, "conversation_id"),
        role=MessageRole(_text(row, "role")),
        content=_text(row, "content"),
        image=ImageArtifact.model_validate_json(image_json) if image_json is not None else None,
        created_at=datetime.fromisoformat(_text(row, "created_at")),
    )


def _text(row: aiosqlite.Row, key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise TurnPersistenceError(f"SQLite column {key} must contain text.")
    return value


def _optional_text(row: aiosqlite.Row, key: str) -> str | None:
    value = row[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise TurnPersistenceError(f"SQLite column {key} must contain text or null.")
    return value


def _complete_turns(messages: tuple[ChatMessage, ...]) -> tuple[CompletedTurn, ...]:
    grouped: dict[str, dict[MessageRole, ChatMessage]] = {}
    order: list[str] = []
    for message in messages:
        if message.turn_id not in grouped:
            grouped[message.turn_id] = {}
            order.append(message.turn_id)
        grouped[message.turn_id][message.role] = message
    return tuple(
        CompletedTurn(
            user=grouped[turn_id][MessageRole.USER],
            assistant=grouped[turn_id][MessageRole.ASSISTANT],
        )
        for turn_id in order
        if MessageRole.USER in grouped[turn_id] and MessageRole.ASSISTANT in grouped[turn_id]
    )
