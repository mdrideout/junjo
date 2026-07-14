"""Focused persistence, renderer, and deterministic demo-driver adapter tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import SequenceClock, SequenceIds, make_harness

from ai_chat.adapters.images import SvgImageRenderer
from ai_chat.adapters.model import demo_model_binding
from ai_chat.adapters.persistence import SqliteChatStore
from ai_chat.domain.errors import TurnPersistenceError
from ai_chat.domain.models import ChatAgentOutput, ImageArtifact, MessageRole


@pytest.mark.asyncio
async def test_sqlite_store_round_trips_complete_turns_search_and_image_artifacts(
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
    user = await store.append_user_message(
        conversation_id="demo",
        turn_id="complete",
        content="The project uses Junjo.",
    )
    assistant = await store.append_assistant_message(
        conversation_id="demo",
        turn_id="complete",
        output=ChatAgentOutput(message="Correct.", image=artifact),
    )
    await store.append_user_message(
        conversation_id="demo",
        turn_id="current",
        content="What did I say?",
    )

    conversations = await store.list_conversations()
    contact = await store.get_contact_for_conversation("demo")
    messages = await store.list_messages("demo")
    completed = await store.completed_turns_before("demo", "current")
    matches = await store.search_history("demo", "current", "project", 5)

    assert [(item.id, item.title) for item in conversations] == [("demo", "Junjo Agent Demo")]
    assert contact.display_name == "Junjo Guide"
    assert messages[0] == user
    assert messages[1] == assistant
    assert messages[1].image == artifact
    assert completed[0].user == user
    assert completed[0].assistant == assistant
    assert [(match.role, match.content) for match in matches] == [(MessageRole.USER, "The project uses Junjo.")]
    with pytest.raises(TurnPersistenceError):
        await store.append_user_message(
            conversation_id="demo",
            turn_id="current",
            content="duplicate",
        )
    await store.close()


@pytest.mark.asyncio
async def test_svg_renderer_writes_one_explicit_application_artifact(tmp_path: Path) -> None:
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
    image = await harness.turns.submit(conversation_id="demo", text="Draw an image of a graph")

    assert direct.assistant_message.content == "Deterministic reply: hello"
    assert "hello" in history.assistant_message.content
    assert "Junjo Guide" in contact.assistant_message.content
    assert image.assistant_message.image is not None
    assert len(harness.renderer.calls) == 1
