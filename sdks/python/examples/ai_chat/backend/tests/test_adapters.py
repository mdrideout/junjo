"""Focused persistence, renderer, and deterministic demo-driver adapter tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import SequenceClock, SequenceIds, make_harness

from ai_chat.adapters.images import SvgImageRenderer
from ai_chat.adapters.model import demo_model_binding
from ai_chat.adapters.persistence import SqliteChatStore
from ai_chat.domain.errors import TurnInProgressError
from ai_chat.domain.models import (
    ChatAgentOutput,
    ContextPolicyReference,
    ImageArtifact,
    MessageRole,
    TurnFailure,
    TurnStatus,
)


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

    assert [(item.conversation.id, item.conversation.title) for item in conversations] == [("demo", "Junjo Agent Demo")]
    assert contact.display_name == "Junjo Guide"
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
async def test_svg_renderer_writes_one_explicit_application_artifact(
    tmp_path: Path,
) -> None:
    renderer = SvgImageRenderer(directory=tmp_path, id_factory=SequenceIds("image"))

    artifact = await renderer.render(prompt="A Junjo graph", alt_text="A graph illustration")

    assert artifact == ImageArtifact(
        id="image-1",
        url="/api/images/image-1.svg",
        alt_text="A graph illustration",
    )
    content = (tmp_path / "image-1.svg").read_text(encoding="utf-8")
    assert "A Junjo graph" in content
    assert "<svg" in content


@pytest.mark.asyncio
async def test_default_demo_driver_runs_direct_history_contact_and_image_paths_without_credentials(
    tmp_path: Path,
) -> None:
    harness = make_harness(tmp_path, binding=demo_model_binding())

    direct = await harness.turns.submit(conversation_id="demo", text="hello")
    history = await harness.turns.submit(conversation_id="demo", text="Remember hello")
    contact = await harness.turns.submit(conversation_id="demo", text="Show the contact profile")
    image = await harness.turns.submit(
        conversation_id="demo",
        text="Make a graph visual",
    )

    assert direct.assistant_message is not None
    assert direct.assistant_message.content == "Deterministic reply: hello"
    assert history.assistant_message is not None
    assert "hello" in history.assistant_message.content
    assert contact.assistant_message is not None
    assert "Junjo Guide" in contact.assistant_message.content
    assert image.assistant_message is not None
    assert image.assistant_message.image is not None
    assert image.execution_references.agent_run_id is not None
    assert len(harness.renderer.calls) == 1
