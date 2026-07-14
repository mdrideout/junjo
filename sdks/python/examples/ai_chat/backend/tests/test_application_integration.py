"""Small integration checks across application Graph, model, and persistence layers."""

from pathlib import Path

import pytest

from ai_chat.domain.models import ContactSex, TurnStatus
from conftest import FakeLanguageModel, make_harness


@pytest.mark.asyncio
async def test_contact_workflow_moves_live_capability_results_into_versioned_persistence(
    tmp_path: Path,
) -> None:
    harness = make_harness(tmp_path)

    created = await harness.application.contacts.create(ContactSex.MALE)
    loaded = await harness.store.get_contact_for_conversation(created.conversation.id)

    assert loaded.object_type == "ai_chat.contact"
    assert loaded.schema_version == 1
    assert loaded.display_name == "Junjo Guide"
    assert loaded.bio.startswith("I coordinate community arts programs")
    assert loaded.avatar.url.endswith("rendered-image.png")
    assert len(harness.images.calls) == 1
    assert any("dating profile biography" in prompt for prompt in harness.language.text_prompts)
    assert any("Create one realistic name" in prompt for prompt in harness.language.structured_prompts)


@pytest.mark.asyncio
async def test_image_directive_runs_shared_avatar_conditioned_workflow_without_agent(
    tmp_path: Path,
) -> None:
    language = FakeLanguageModel(directive="image_response")
    harness = make_harness(tmp_path, language=language)

    completed = await harness.turns.submit(
        conversation_id="demo",
        text="Can you send a picture?",
    )

    assert completed.status is TurnStatus.COMPLETED
    assert completed.assistant_message is not None
    assert completed.assistant_message.image is not None
    assert completed.assistant_message.image.url.endswith("edited-image.png")
    assert completed.execution_references.agent_run_id is None
    assert len(harness.images.calls) == 1
