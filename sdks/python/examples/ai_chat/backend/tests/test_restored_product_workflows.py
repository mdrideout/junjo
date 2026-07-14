"""Acceptance coverage for restored product behavior around the Agent proof."""

from pathlib import Path

import pytest
from conftest import make_harness
from junjo.agent import FinalOutputResponse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ai_chat.domain.models import ContactSex


@pytest.mark.asyncio
async def test_contact_creation_keeps_concurrency_avatar_subflow_and_persistence(
    tmp_path: Path,
    span_exporter: InMemorySpanExporter,
) -> None:
    harness = make_harness(tmp_path)

    result = await harness.application.contacts.create(ContactSex.FEMALE)

    assert result.contact.sex is ContactSex.FEMALE
    assert result.conversation.contact_id == result.contact.id
    assert result.contact.avatar.url == "/api/images/rendered-image.svg"
    conversations = await harness.store.list_conversations()
    assert {item.conversation.id for item in conversations} == {
        "demo",
        result.conversation.id,
    }
    names = {span.name for span in span_exporter.get_finished_spans()}
    assert {
        "Create Contact Workflow",
        "Create Initial Contact Data",
        "SelectAgeNode",
        "SelectLocationNode",
        "SelectPersonalityNode",
        "Create Contact Avatar Subflow",
        "RenderAvatarNode",
        "PersistContactNode",
    } <= names


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "expected_fragment"),
    [
        ("I need help with a work problem", "first step"),
        ("Suggest a date night", "For a date"),
    ],
)
async def test_specialized_message_branches_do_not_create_agent_runs(
    tmp_path: Path,
    text: str,
    expected_fragment: str,
) -> None:
    harness = make_harness(tmp_path)

    result = await harness.turns.submit(conversation_id="demo", text=text)

    assert result.assistant_message is not None
    assert expected_fragment in result.assistant_message.content
    assert result.execution_references.agent_run_id is None
    assert harness.driver is not None
    assert harness.driver.requests == ()


@pytest.mark.asyncio
async def test_general_branch_is_the_workflow_to_agent_boundary(tmp_path: Path) -> None:
    harness = make_harness(
        tmp_path,
        script=[
            FinalOutputResponse(
                output={"message": "A bounded Agent response.", "image": None}
            )
        ],
    )

    result = await harness.turns.submit(conversation_id="demo", text="Hello there")

    assert result.assistant_message is not None
    assert result.assistant_message.content == "A bounded Agent response."
    assert result.execution_references.agent_run_id is not None
