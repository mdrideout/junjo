"""Composition root for the runnable SQLite application."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from junjo import ModelDriverBinding

from ai_chat.adapters.images import GeminiImageModel, GrokImageModel
from ai_chat.adapters.model import (
    GeminiLanguageModel,
    GrokLanguageModel,
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
from ai_chat.domain.ports import ApplicationStore, ImageModel, LanguageModel


def new_id() -> str:
    return uuid4().hex


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class ChatApplication:
    store: ApplicationStore
    turns: ChatTurnService
    contacts: ContactCreationService
    images: ImageModel
    image_directory: Path
    debug: DebugSettings = DebugSettings(enabled=False, studio_ui_url=None)
    _turn_tasks: set[asyncio.Task[None]] = field(default_factory=set, init=False)

    async def initialize(self) -> None:
        self.image_directory.mkdir(parents=True, exist_ok=True)
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
    language: LanguageModel | None = None,
    images: ImageModel | None = None,
) -> ChatApplication:
    store = SqliteChatStore(
        path=settings.database_path,
        id_factory=new_id,
        clock=utc_now,
    )
    supplied = (model, language, images)
    if all(value is not None for value in supplied):
        assert model is not None
        assert language is not None
        assert images is not None
        model_binding = model
        language_model = language
        image_model = images
    elif any(value is not None for value in supplied):
        raise ValueError("Tests must supply model, language, and images together.")
    else:
        model_binding, language_model, image_model = _provider_bindings(settings)
    agent = create_chat_agent(model_binding)
    turns = ChatTurnService(
        agent=agent,
        turns=store,
        history=store,
        contacts=store,
        language=language_model,
        images=image_model,
        id_factory=new_id,
    )
    contacts = ContactCreationService(
        contacts=store,
        language=language_model,
        images=image_model,
        id_factory=new_id,
    )
    return ChatApplication(
        store=store,
        turns=turns,
        contacts=contacts,
        images=image_model,
        image_directory=settings.image_directory,
        debug=settings.debug,
    )


def _provider_bindings(
    settings: Settings,
) -> tuple[ModelDriverBinding, LanguageModel, ImageModel]:
    if settings.model_provider is ModelProvider.GEMINI:
        assert settings.gemini_api_key is not None
        return (
            gemini_model_binding(
                api_key=settings.gemini_api_key,
                model=settings.gemini_text_model,
            ),
            GeminiLanguageModel(
                api_key=settings.gemini_api_key,
                model=settings.gemini_text_model,
            ),
            GeminiImageModel(
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
        GrokLanguageModel(
            api_key=settings.xai_api_key,
            model=settings.grok_text_model,
        ),
        GrokImageModel(
            api_key=settings.xai_api_key,
            model=settings.grok_image_model,
            directory=settings.image_directory,
            id_factory=new_id,
        ),
    )
