"""Deterministic collaborators for application infrastructure tests only."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import count
from pathlib import Path
from typing import TypeVar

import pytest
from junjo import AgentLimits, ModelDriverBinding, ModelDriverDescriptor
from junjo.agent.testing import ScriptedModelDriver
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from ai_chat.adapters.persistence import InMemoryChatStore
from ai_chat.application.chat_agent import create_chat_agent
from ai_chat.application.contact_workflow import ContactCreationService
from ai_chat.application.turn_workflow import ChatTurnService
from ai_chat.bootstrap import ChatApplication
from ai_chat.domain.models import (
    ContactProfile,
    ContactSex,
    Conversation,
    ImageArtifact,
    ImageEditResult,
    PersonalityTraits,
)

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


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


class FakeLanguageModel:
    """Transport-test collaborator; it is not a product-quality oracle."""

    def __init__(self, *, directive: str = "general_response") -> None:
        self.directive = directive
        self.text_prompts: list[str] = []
        self.structured_prompts: list[str] = []

    async def generate_text(self, *, prompt: str) -> str:
        self.text_prompts.append(prompt)
        if "photography idea" in prompt:
            return "A candid outdoor portrait after a neighborhood walk."
        if "dating profile biography" in prompt:
            return (
                "I coordinate community arts programs and spend weekends trying new recipes, "
                "walking through Brooklyn, and visiting family."
            )
        if "accompany the generated photo" in prompt:
            return "Thought you might like this one."
        return "A model-generated application response."

    async def generate_structured(
        self,
        *,
        prompt: str,
        output_type: type[StructuredOutput],
    ) -> StructuredOutput:
        self.structured_prompts.append(prompt)
        values: dict[str, object]
        if output_type.__name__ == "LocationResult":
            values = {"city": "Brooklyn", "state": "NY"}
        elif output_type.__name__ == "NameResult":
            values = {"first_name": "Junjo", "last_name": "Guide"}
        elif output_type.__name__ == "DirectiveDecision":
            values = {"directive": self.directive}
        else:
            raise AssertionError(f"Unexpected structured output: {output_type.__name__}")
        return output_type.model_validate(values)


class RecordingImageModel:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def generate(self, *, prompt: str, alt_text: str) -> ImageArtifact:
        self.calls.append((prompt, alt_text))
        return ImageArtifact(
            id="rendered-image",
            url="/api/images/rendered-image.png",
            alt_text=alt_text,
        )

    async def edit(
        self,
        *,
        source: ImageArtifact,
        prompt: str,
        alt_text: str,
    ) -> ImageEditResult:
        self.calls.append((prompt, alt_text))
        return ImageEditResult(
            artifact=ImageArtifact(
                id="edited-image",
                url="/api/images/edited-image.png",
                alt_text=alt_text,
            ),
            text="A model-generated image response.",
        )


@dataclass(slots=True)
class Harness:
    store: InMemoryChatStore
    images: RecordingImageModel
    language: FakeLanguageModel
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
    images: RecordingImageModel | None = None,
    language: FakeLanguageModel | None = None,
    limits: AgentLimits | None = None,
    id_factory: Callable[[], str] | None = None,
    include_second_conversation: bool = False,
) -> Harness:
    ids = id_factory or SequenceIds()
    store = InMemoryChatStore(
        conversations=(
            Conversation(id="demo", title="Demo conversation", contact_id="contact-1"),
            *(
                (Conversation(id="demo-2", title="Second conversation", contact_id="contact-1"),)
                if include_second_conversation
                else ()
            ),
        ),
        contacts=(
            sample_contact(),
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
    language_model = language or FakeLanguageModel()
    image_model = images or RecordingImageModel()
    agent = create_chat_agent(model, limits=limits)
    turns = ChatTurnService(
        agent=agent,
        turns=store,
        history=store,
        contacts=store,
        language=language_model,
        images=image_model,
        id_factory=ids,
    )
    contacts = ContactCreationService(
        contacts=store,
        language=language_model,
        images=image_model,
        id_factory=ids,
    )
    image_directory.mkdir(parents=True, exist_ok=True)
    application = ChatApplication(
        store=store,
        turns=turns,
        contacts=contacts,
        images=image_model,
        image_directory=image_directory,
    )
    return Harness(
        store=store,
        images=image_model,
        language=language_model,
        turns=turns,
        application=application,
        driver=driver,
    )


def sample_contact() -> ContactProfile:
    return ContactProfile(
        id="contact-1",
        first_name="Junjo",
        last_name="Guide",
        sex=ContactSex.FEMALE,
        age=31,
        personality=PersonalityTraits(
            openness=0.8,
            conscientiousness=0.6,
            extraversion=0.7,
            agreeableness=0.8,
            neuroticism=0.2,
            intelligence=0.8,
            religiousness=0.1,
            attractiveness=0.8,
            trauma=0.2,
        ),
        latitude=40.6782,
        longitude=-73.9442,
        city="Brooklyn",
        state="NY",
        bio="A deterministic application contact.",
        avatar=ImageArtifact(
            id="avatar-1",
            url="/api/images/avatar-1.png",
            alt_text="Portrait of Junjo Guide",
        ),
    )
