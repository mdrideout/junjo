"""Composition root for the runnable SQLite application."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from google import genai
from junjo import ModelDriverBinding
from xai_sdk import AsyncClient

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
from ai_chat.config import ModelProvider, Settings, StudioDiagnosticsSettings
from ai_chat.domain.errors import TurnExecutionError
from ai_chat.domain.models import ConversationOverview, Turn
from ai_chat.domain.ports import ApplicationStore, ImageModel, LanguageModel

logger = logging.getLogger(__name__)

AsyncClose = Callable[[], Awaitable[None]]
ImageModelFactory = Callable[[Path], ImageModel]


def new_id() -> str:
    return uuid4().hex


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ProviderRuntime:
    """One application-owned provider client and its narrow capabilities."""

    model: ModelDriverBinding
    language: LanguageModel
    images: ImageModel
    _image_model_factory: ImageModelFactory
    _close_client: AsyncClose

    def images_for_directory(self, directory: Path) -> ImageModel:
        """Bind image artifacts to one application-owned directory."""

        return self._image_model_factory(directory)

    async def close(self) -> None:
        await self._close_client()


@dataclass(slots=True)
class ChatApplication:
    store: ApplicationStore
    turns: ChatTurnService
    contacts: ContactCreationService
    images: ImageModel
    image_directory: Path
    provider_runtime: ProviderRuntime | None = None
    studio_diagnostics: StudioDiagnosticsSettings = StudioDiagnosticsSettings(frontend_base_url=None)
    _turn_tasks: set[asyncio.Task[None]] = field(default_factory=set, init=False)

    async def initialize(self) -> None:
        self.image_directory.mkdir(parents=True, exist_ok=True)
        await self.store.initialize()

    async def close(self) -> None:
        for task in tuple(self._turn_tasks):
            task.cancel("application_shutdown")
        errors: list[BaseException] = []
        if self._turn_tasks:
            try:
                await asyncio.gather(*self._turn_tasks, return_exceptions=True)
            except BaseException as error:
                errors.append(error)
        try:
            await self.store.close()
        except BaseException as error:
            errors.append(error)
        try:
            if self.provider_runtime is not None:
                await self.provider_runtime.close()
        except BaseException as error:
            errors.append(error)
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise BaseExceptionGroup("application cleanup failed", errors)

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
        except TurnExecutionError as error:
            # The service has already persisted safe terminal failure evidence.
            logger.exception(
                "Turn execution failed (turn_id=%s, workflow_run_id=%s, agent_run_id=%s)",
                error.turn_id,
                error.workflow_run_id,
                error.agent_run_id,
            )
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
    provider_runtime: ProviderRuntime | None = None
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
        provider_runtime = build_provider_runtime(settings)
        model_binding = provider_runtime.model
        language_model = provider_runtime.language
        image_model = provider_runtime.images
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
        provider_runtime=provider_runtime,
        studio_diagnostics=settings.studio_diagnostics,
    )


def build_provider_runtime(settings: Settings) -> ProviderRuntime:
    """Construct one command- or application-owned live provider runtime."""

    if settings.model_provider is ModelProvider.GEMINI:
        assert settings.gemini_api_key is not None
        gemini_client = genai.Client(api_key=settings.gemini_api_key).aio

        def image_model(directory: Path) -> ImageModel:
            return GeminiImageModel(
                client=gemini_client,
                model=settings.gemini_image_model,
                timeout_seconds=settings.provider_timeout_seconds,
                directory=directory,
                id_factory=new_id,
            )

        return ProviderRuntime(
            model=gemini_model_binding(
                client=gemini_client,
                model=settings.gemini_text_model,
                timeout_seconds=settings.provider_timeout_seconds,
            ),
            language=GeminiLanguageModel(
                client=gemini_client,
                model=settings.gemini_text_model,
                timeout_seconds=settings.provider_timeout_seconds,
            ),
            images=image_model(settings.image_directory),
            _image_model_factory=image_model,
            _close_client=gemini_client.aclose,
        )
    assert settings.xai_api_key is not None
    xai_client = AsyncClient(
        api_key=settings.xai_api_key,
        timeout=settings.provider_timeout_seconds,
    )

    def image_model(directory: Path) -> ImageModel:
        return GrokImageModel(
            client=xai_client,
            model=settings.grok_image_model,
            timeout_seconds=settings.provider_timeout_seconds,
            directory=directory,
            id_factory=new_id,
        )

    return ProviderRuntime(
        model=grok_model_binding(
            client=xai_client,
            model=settings.grok_text_model,
            timeout_seconds=settings.provider_timeout_seconds,
        ),
        language=GrokLanguageModel(
            client=xai_client,
            model=settings.grok_text_model,
            timeout_seconds=settings.provider_timeout_seconds,
        ),
        images=image_model(settings.image_directory),
        _image_model_factory=image_model,
        _close_client=xai_client.close,
    )
