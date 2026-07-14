"""Composition root for the runnable SQLite application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ai_chat.adapters.images import SvgImageRenderer
from ai_chat.adapters.model import demo_model_binding
from ai_chat.adapters.persistence import SqliteChatStore
from ai_chat.application.chat_agent import create_chat_agent
from ai_chat.application.turn_workflow import ChatTurnService
from ai_chat.config import Settings
from ai_chat.domain.models import ChatMessage, Conversation
from ai_chat.domain.ports import ApplicationStore


def new_id() -> str:
    return uuid4().hex


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class ChatApplication:
    store: ApplicationStore
    turns: ChatTurnService
    image_directory: Path

    async def initialize(self) -> None:
        await self.store.initialize()

    async def close(self) -> None:
        await self.store.close()

    async def list_conversations(self) -> tuple[Conversation, ...]:
        return await self.store.list_conversations()

    async def list_messages(self, conversation_id: str) -> tuple[ChatMessage, ...]:
        return await self.store.list_messages(conversation_id)


def build_application(settings: Settings) -> ChatApplication:
    store = SqliteChatStore(
        path=settings.database_path,
        id_factory=new_id,
        clock=utc_now,
    )
    images = SvgImageRenderer(directory=settings.image_directory, id_factory=new_id)
    agent = create_chat_agent(demo_model_binding())
    turns = ChatTurnService(
        agent=agent,
        messages=store,
        history=store,
        contacts=store,
        images=images,
        id_factory=new_id,
    )
    return ChatApplication(store=store, turns=turns, image_directory=settings.image_directory)
