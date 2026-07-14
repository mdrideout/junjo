"""Deterministic application collaborators shared by Horizon 2 tests."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import count
from pathlib import Path

import pytest
from junjo import AgentLimits, ModelDriverBinding, ModelDriverDescriptor
from junjo.agent.testing import ScriptedModelDriver
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ai_chat.adapters.persistence import InMemoryChatStore
from ai_chat.application.chat_agent import create_chat_agent
from ai_chat.application.turn_workflow import ChatTurnService
from ai_chat.bootstrap import ChatApplication
from ai_chat.domain.models import ContactProfile, Conversation, ImageArtifact


@pytest.fixture
def span_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(trace._TRACER_PROVIDER_SET_ONCE, "_done", True)
    return exporter


class SequenceIds:
    def __init__(self, prefix: str = "id") -> None:
        self._prefix = prefix
        self._values = count(1)

    def __call__(self) -> str:
        return f"{self._prefix}-{next(self._values)}"


class SequenceClock:
    def __init__(self) -> None:
        self._start = datetime(2026, 7, 14, tzinfo=UTC)
        self._values = count()

    def __call__(self) -> datetime:
        return self._start + timedelta(microseconds=next(self._values))


class RecordingImageRenderer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def render(self, *, prompt: str, alt_text: str) -> ImageArtifact:
        self.calls.append((prompt, alt_text))
        return ImageArtifact(
            id="rendered-image",
            url="/api/images/rendered-image.svg",
            alt_text=alt_text,
        )


@dataclass(slots=True)
class Harness:
    store: InMemoryChatStore
    renderer: RecordingImageRenderer
    turns: ChatTurnService
    application: ChatApplication
    driver: ScriptedModelDriver | None


def scripted_descriptor() -> ModelDriverDescriptor:
    return ModelDriverDescriptor(
        driver_key="horizon_2_scripted",
        provider="junjo",
        model="scripted-v1",
        settings={},
    )


def make_harness(
    image_directory: Path,
    *,
    script: Sequence[object] = (),
    binding: ModelDriverBinding | None = None,
    renderer: RecordingImageRenderer | None = None,
    limits: AgentLimits | None = None,
    id_factory: Callable[[], str] | None = None,
) -> Harness:
    ids = id_factory or SequenceIds()
    store = InMemoryChatStore(
        conversations=(Conversation(id="demo", title="Demo conversation", contact_id="contact-1"),),
        contacts=(
            ContactProfile(
                id="contact-1",
                display_name="Junjo Guide",
                bio="A deterministic application contact.",
            ),
        ),
        id_factory=ids,
        clock=SequenceClock(),
    )
    driver: ScriptedModelDriver | None = None
    model = binding
    if model is None:
        driver = ScriptedModelDriver(script)
        model = ModelDriverBinding.shared(
            descriptor=scripted_descriptor(),
            driver=driver,
        )
    image_renderer = renderer or RecordingImageRenderer()
    agent = create_chat_agent(model, limits=limits)
    turns = ChatTurnService(
        agent=agent,
        messages=store,
        history=store,
        contacts=store,
        images=image_renderer,
        id_factory=ids,
    )
    image_directory.mkdir(parents=True, exist_ok=True)
    application = ChatApplication(
        store=store,
        turns=turns,
        image_directory=image_directory,
    )
    return Harness(
        store=store,
        renderer=image_renderer,
        turns=turns,
        application=application,
        driver=driver,
    )
