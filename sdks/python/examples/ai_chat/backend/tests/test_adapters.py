"""Focused persistence tests for versioned application objects and Turns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from ai_chat.adapters.images import GrokImageModel
from ai_chat.adapters.persistence import SqliteChatStore
from ai_chat.domain.errors import TurnInProgressError
from ai_chat.domain.models import (
    ChatAgentOutput,
    ContextPolicyReference,
    Conversation,
    ImageArtifact,
    MessageRole,
    TurnFailure,
    TurnStatus,
)
from conftest import SequenceClock, SequenceIds, sample_contact


class FakeGrokImageResponse:
    def __init__(self, image_bytes: bytes) -> None:
        self._image_bytes = image_bytes

    @property
    async def image(self) -> bytes:
        return self._image_bytes


class FakeGrokImageClient:
    def __init__(self, image_bytes: bytes) -> None:
        self.image = self
        self._image_bytes = image_bytes
        self.requests: list[dict[str, Any]] = []

    async def sample(self, **request: Any) -> FakeGrokImageResponse:
        self.requests.append(request)
        return FakeGrokImageResponse(self._image_bytes)


@pytest.mark.asyncio
async def test_sqlite_store_round_trips_versioned_turns_search_and_image_artifacts(
    tmp_path: Path,
) -> None:
    store = SqliteChatStore(
        path=tmp_path / "chat.sqlite3",
        id_factory=SequenceIds("sqlite"),
        clock=SequenceClock(),
    )
    await store.initialize()
    contact = sample_contact()
    await store.create_contact(
        contact=contact,
        conversation=Conversation(id="demo", title=contact.display_name, contact_id=contact.id),
    )
    artifact = ImageArtifact(
        id="image",
        url="/api/images/image.svg",
        alt_text="A persisted image",
    )
    admitted = await store.admit_turn(
        conversation_id="demo",
        turn_id="complete",
        text="The project uses Junjo.",
        context_policy=ContextPolicyReference(),
    )
    running = await store.start_turn(admitted.id)
    with_outcome = await store.record_turn_outcome(
        turn_id=running.id,
        output=ChatAgentOutput(message="Correct.", image=artifact),
        agent_run_id="agent-run",
    )
    completed_turn = await store.complete_turn(
        turn_id=with_outcome.id,
        workflow_run_id="workflow-run",
    )
    current = await store.admit_turn(
        conversation_id="demo",
        turn_id="current",
        text="What did I say?",
        context_policy=ContextPolicyReference(),
    )

    conversations = await store.list_conversations()
    contact = await store.get_contact_for_conversation("demo")
    turns = await store.list_turns("demo")
    completed = await store.recent_completed_turns("demo", current.sequence, 8)
    matches = await store.search_history("demo", current.sequence, "project", 5)

    assert [(item.conversation.id, item.conversation.title) for item in conversations] == [("demo", "Junjo Guide")]
    assert contact.display_name == "Junjo Guide"
    assert contact.object_type == "ai_chat.contact"
    assert contact.personality.openness == 0.8
    assert turns == (completed_turn, current)
    assert turns[0].object_type == "ai_chat.turn"
    assert turns[0].schema_version == 1
    assert turns[0].status is TurnStatus.COMPLETED
    assert turns[0].assistant_message is not None
    assert turns[0].assistant_message.image == artifact
    assert completed[0].user == completed_turn.user_message
    assert completed[0].assistant == completed_turn.assistant_message
    assert [(match.role, match.content) for match in matches] == [(MessageRole.USER, "The project uses Junjo.")]
    with pytest.raises(TurnInProgressError):
        await store.admit_turn(
            conversation_id="demo",
            turn_id="current",
            text="duplicate",
            context_policy=ContextPolicyReference(),
        )
    await store.close()


@pytest.mark.asyncio
async def test_sqlite_recent_context_skips_terminal_failures_before_applying_limit(
    tmp_path: Path,
) -> None:
    store = SqliteChatStore(
        path=tmp_path / "chat.sqlite3",
        id_factory=SequenceIds("sqlite"),
        clock=SequenceClock(),
    )
    await store.initialize()
    contact = sample_contact()
    await store.create_contact(
        contact=contact,
        conversation=Conversation(id="demo", title=contact.display_name, contact_id=contact.id),
    )
    first = await store.admit_turn(
        conversation_id="demo",
        turn_id="completed",
        text="completed input",
        context_policy=ContextPolicyReference(),
    )
    await store.start_turn(first.id)
    await store.record_turn_outcome(
        turn_id=first.id,
        output=ChatAgentOutput(message="completed output"),
        agent_run_id="agent-run",
    )
    await store.complete_turn(turn_id=first.id, workflow_run_id="workflow-run")
    failed = await store.admit_turn(
        conversation_id="demo",
        turn_id="failed",
        text="failed input",
        context_policy=ContextPolicyReference(),
    )
    await store.start_turn(failed.id)
    await store.terminate_turn(
        turn_id=failed.id,
        status=TurnStatus.FAILED,
        failure=TurnFailure(code="failed", detail="failed"),
        workflow_run_id="failed-workflow-run",
        agent_run_id=None,
    )
    current = await store.admit_turn(
        conversation_id="demo",
        turn_id="current",
        text="current",
        context_policy=ContextPolicyReference(),
    )

    recent = await store.recent_completed_turns("demo", current.sequence, 1)

    assert [turn.user.turn_id for turn in recent] == ["completed"]
    await store.close()


@pytest.mark.asyncio
async def test_sqlite_startup_reconciles_all_abandoned_turns_and_unblocks_conversations(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "chat.sqlite3"
    store = SqliteChatStore(
        path=database_path,
        id_factory=SequenceIds("before-restart"),
        clock=SequenceClock(),
    )
    await store.initialize()
    first_contact = sample_contact()
    second_contact = first_contact.model_copy(update={"id": "contact-2", "first_name": "Second"})
    await store.create_contact(
        contact=first_contact,
        conversation=Conversation(
            id="admitted-conversation",
            title=first_contact.display_name,
            contact_id=first_contact.id,
        ),
    )
    await store.create_contact(
        contact=second_contact,
        conversation=Conversation(
            id="running-conversation",
            title=second_contact.display_name,
            contact_id=second_contact.id,
        ),
    )
    admitted = await store.admit_turn(
        conversation_id="admitted-conversation",
        turn_id="abandoned-admitted",
        text="admitted",
        context_policy=ContextPolicyReference(),
    )
    running = await store.admit_turn(
        conversation_id="running-conversation",
        turn_id="abandoned-running",
        text="running",
        context_policy=ContextPolicyReference(),
    )
    await store.start_turn(running.id)
    await store.record_turn_outcome(
        turn_id=running.id,
        output=ChatAgentOutput(message="Persisted before interruption."),
        agent_run_id="known-agent-run",
    )
    await store.close()

    restarted = SqliteChatStore(
        path=database_path,
        id_factory=SequenceIds("after-restart"),
        clock=SequenceClock(),
    )
    await restarted.initialize()

    reconciled_admitted = await restarted.get_turn(admitted.id)
    reconciled_running = await restarted.get_turn(running.id)
    for turn in (reconciled_admitted, reconciled_running):
        assert turn.status is TurnStatus.FAILED
        assert turn.failure is not None
        assert turn.failure.code == "turn_interrupted"
        assert turn.failure.termination_reason == "process_interrupted"
        assert turn.completed_at is not None
    assert reconciled_running.execution_references.agent_run_id == "known-agent-run"
    assert reconciled_running.assistant_message is not None

    next_admitted = await restarted.admit_turn(
        conversation_id="admitted-conversation",
        turn_id="after-interruption",
        text="The conversation is no longer blocked.",
        context_policy=ContextPolicyReference(),
    )
    assert next_admitted.sequence == 2
    await restarted.close()


@pytest.mark.asyncio
async def test_grok_image_adapter_awaits_and_persists_sdk_image_response(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "fixture.png"
    Image.new("RGB", (2, 2), color="purple").save(source_path, format="PNG")
    image_bytes = source_path.read_bytes()
    client = FakeGrokImageClient(image_bytes)
    image_directory = tmp_path / "images"
    image_directory.mkdir()
    images = GrokImageModel(
        client=client,  # type: ignore[arg-type]
        model="grok-imagine-image-quality",
        timeout_seconds=1,
        directory=image_directory,
        id_factory=SequenceIds("grok-image"),
    )

    generated = await images.generate(prompt="portrait", alt_text="Generated portrait")
    edited = await images.edit(
        source=generated,
        prompt="new setting",
        alt_text="Edited portrait",
    )

    assert generated.url.endswith(".png")
    assert edited.artifact.url.endswith(".png")
    assert (image_directory / f"{generated.id}.png").is_file()
    assert (image_directory / f"{edited.artifact.id}.png").is_file()
    assert client.requests[0]["image_format"] == "base64"
    assert client.requests[0]["aspect_ratio"] == "1:1"
    assert client.requests[1]["image_url"].startswith("data:image/png;base64,")
