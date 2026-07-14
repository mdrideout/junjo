"""Composition root for the runnable SQLite application."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from junjo import ModelDriverBinding

from ai_chat.adapters.images import (
    GeminiImageRenderer,
    GrokImageRenderer,
    SvgImageRenderer,
    ensure_seed_avatar,
)
from ai_chat.adapters.model import (
    demo_model_binding,
    gemini_model_binding,
    grok_model_binding,
)
from ai_chat.adapters.persistence import SqliteChatStore
from ai_chat.application.chat_agent import create_chat_agent
from ai_chat.application.contact_workflow import ContactCreationService
from ai_chat.application.turn_workflow import ChatTurnService
from ai_chat.config import DebugSettings, ModelProvider, Settings
from ai_chat.domain.errors import TurnExecutionError
from ai_chat.domain.models import ConversationOverview, Turn
from ai_chat.domain.ports import ApplicationStore, ImageRenderer


def new_id() -> str:
    return uuid4().hex


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class ChatApplication:
    store: ApplicationStore
    turns: ChatTurnService
    contacts: ContactCreationService
    images: ImageRenderer
    image_directory: Path
    debug: DebugSettings = DebugSettings(enabled=False, studio_ui_url=None)
    _turn_tasks: set[asyncio.Task[None]] = field(default_factory=set, init=False)

    async def initialize(self) -> None:
        ensure_seed_avatar(self.image_directory)
        await self.store.initialize()

    async def close(self) -> None:
        for task in tuple(self._turn_tasks):
            task.cancel("application_shutdown")
        if self._turn_tasks:
            await asyncio.gather(*self._turn_tasks, return_exceptions=True)
        await self.store.close()

    async def list_conversations(self) -> tuple[ConversationOverview, ...]:
        return await self.store.list_conversations()

    async def list_turns(self, conversation_id: str) -> tuple[Turn, ...]:
        return await self.store.list_turns(conversation_id)

    async def admit_turn(self, *, conversation_id: str, text: str) -> Turn:
        turn = await self.turns.admit(conversation_id=conversation_id, text=text)
        task = asyncio.create_task(
            self._execute_turn(turn.id),
            name=f"ai-chat-turn-{turn.id}",
        )
        self._turn_tasks.add(task)
        task.add_done_callback(self._turn_tasks.discard)
        return turn

    async def _execute_turn(self, turn_id: str) -> None:
        try:
            await self.turns.execute(turn_id)
        except TurnExecutionError:
            # The service has already persisted safe terminal failure evidence.
            return


def build_application(
    settings: Settings,
    *,
    model: ModelDriverBinding | None = None,
) -> ChatApplication:
    store = SqliteChatStore(
        path=settings.database_path,
        id_factory=new_id,
        clock=utc_now,
    )
    configured_model, images = _provider_bindings(settings)
    agent = create_chat_agent(model or configured_model)
    turns = ChatTurnService(
        agent=agent,
        turns=store,
        history=store,
        contacts=store,
        images=images,
        id_factory=new_id,
    )
    contacts = ContactCreationService(
        contacts=store,
        images=images,
        id_factory=new_id,
    )
    return ChatApplication(
        store=store,
        turns=turns,
        contacts=contacts,
        images=images,
        image_directory=settings.image_directory,
        debug=settings.debug,
    )


def _provider_bindings(
    settings: Settings,
) -> tuple[ModelDriverBinding, ImageRenderer]:
    if settings.model_provider is ModelProvider.DEMO:
        return (
            demo_model_binding(),
            SvgImageRenderer(
                directory=settings.image_directory,
                id_factory=new_id,
            ),
        )
    if settings.model_provider is ModelProvider.GEMINI:
        assert settings.gemini_api_key is not None
        return (
            gemini_model_binding(
                api_key=settings.gemini_api_key,
                model=settings.gemini_text_model,
            ),
            GeminiImageRenderer(
                api_key=settings.gemini_api_key,
                model=settings.gemini_image_model,
                directory=settings.image_directory,
                id_factory=new_id,
            ),
        )
    assert settings.xai_api_key is not None
    return (
        grok_model_binding(
            api_key=settings.xai_api_key,
            model=settings.grok_text_model,
        ),
        GrokImageRenderer(
            api_key=settings.xai_api_key,
            model=settings.grok_image_model,
            directory=settings.image_directory,
            id_factory=new_id,
        ),
    )
