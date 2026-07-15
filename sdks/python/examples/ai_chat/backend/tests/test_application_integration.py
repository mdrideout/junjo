"""Small integration checks across application Graph, model, and persistence layers."""

import asyncio
from pathlib import Path

import pytest
from junjo import ModelDriverBinding, WorkflowCancelledError, WorkflowExecutionError
from junjo.agent import AgentModelError, FinalOutputResponse, ModelRequest
from junjo.agent.testing import ScriptedError

from ai_chat.domain.errors import TurnExecutionError
from ai_chat.domain.models import ContactSex, TurnStatus
from conftest import FakeLanguageModel, make_harness, scripted_descriptor


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


@pytest.mark.asyncio
async def test_cancelled_turn_persists_its_outer_workflow_identity(tmp_path: Path) -> None:
    entered = asyncio.Event()

    class BlockingDriver:
        async def request(self, request: ModelRequest) -> object:
            entered.set()
            await asyncio.Future()

    harness = make_harness(
        tmp_path,
        binding=ModelDriverBinding.shared(
            descriptor=scripted_descriptor(),
            driver=BlockingDriver(),
        ),
    )
    turn = await harness.turns.admit(conversation_id="demo", text="Keep working")
    task = asyncio.create_task(harness.turns.execute(turn.id))
    await asyncio.wait_for(entered.wait(), timeout=0.2)

    task.cancel("test cancellation")
    with pytest.raises(WorkflowCancelledError) as raised:
        await task

    persisted = await harness.store.get_turn(turn.id)
    assert persisted.status is TurnStatus.CANCELLED
    assert persisted.execution_references.workflow_run_id == raised.value.run_id
    assert persisted.failure is not None
    assert persisted.failure.termination_reason == "cancelled"


@pytest.mark.asyncio
async def test_failed_turn_retains_workflow_and_agent_error_boundaries(
    tmp_path: Path,
) -> None:
    provider_failure = RuntimeError("provider failed")
    harness = make_harness(tmp_path, script=[ScriptedError(provider_failure)])

    with pytest.raises(TurnExecutionError) as raised:
        await harness.turns.submit(conversation_id="demo", text="Hello")

    workflow_error = raised.value.__cause__
    assert isinstance(workflow_error, WorkflowExecutionError)
    agent_error = workflow_error.__cause__
    assert isinstance(agent_error, AgentModelError)
    assert agent_error.__cause__ is provider_failure
    persisted = await harness.store.get_turn(raised.value.turn_id)
    assert persisted.execution_references.workflow_run_id == workflow_error.run_id
    assert persisted.execution_references.agent_run_id == agent_error.run_id


@pytest.mark.asyncio
async def test_post_workflow_completion_failure_preserves_both_execution_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(
        tmp_path,
        script=[FinalOutputResponse(output={"message": "Hello", "image": None})],
    )

    async def fail_completion(*_args: object, **_kwargs: object):
        raise RuntimeError("completion persistence failed")

    monkeypatch.setattr(type(harness.store), "complete_turn", fail_completion)

    with pytest.raises(TurnExecutionError) as raised:
        await harness.turns.submit(conversation_id="demo", text="Hello")

    assert isinstance(raised.value.__cause__, RuntimeError)
    persisted = await harness.store.get_turn(raised.value.turn_id)
    assert persisted.status is TurnStatus.FAILED
    assert persisted.execution_references.workflow_run_id is not None
    assert persisted.execution_references.agent_run_id is not None


@pytest.mark.asyncio
async def test_cancellation_after_workflow_success_finishes_selected_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(
        tmp_path,
        script=[FinalOutputResponse(output={"message": "Hello", "image": None})],
    )
    completion_entered = asyncio.Event()
    release_completion = asyncio.Event()
    original_completion = type(harness.store).complete_turn

    async def blocked_completion(*args: object, **kwargs: object):
        completion_entered.set()
        await release_completion.wait()
        return await original_completion(*args, **kwargs)

    monkeypatch.setattr(type(harness.store), "complete_turn", blocked_completion)
    task = asyncio.create_task(harness.turns.submit(conversation_id="demo", text="Hello"))
    await asyncio.wait_for(completion_entered.wait(), timeout=0.2)

    task.cancel("caller stopped after Workflow success")
    release_completion.set()
    with pytest.raises(asyncio.CancelledError, match="caller stopped"):
        await task

    turns = await harness.store.list_turns("demo")
    persisted = turns[-1]
    assert persisted.status is TurnStatus.COMPLETED
    assert persisted.execution_references.workflow_run_id is not None
    assert persisted.execution_references.agent_run_id is not None


@pytest.mark.asyncio
async def test_cancellation_after_agent_success_recovers_agent_id_from_workflow_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = make_harness(
        tmp_path,
        script=[FinalOutputResponse(output={"message": "Hello", "image": None})],
    )
    persistence_entered = asyncio.Event()

    async def blocked_outcome(*_args: object, **_kwargs: object):
        persistence_entered.set()
        await asyncio.Future()

    monkeypatch.setattr(type(harness.store), "record_turn_outcome", blocked_outcome)
    turn = await harness.turns.admit(conversation_id="demo", text="Hello")
    task = asyncio.create_task(harness.turns.execute(turn.id))
    await asyncio.wait_for(persistence_entered.wait(), timeout=0.2)

    task.cancel("caller stopped before outcome persistence")
    with pytest.raises(WorkflowCancelledError) as raised:
        await task

    persisted = await harness.store.get_turn(turn.id)
    assert persisted.status is TurnStatus.CANCELLED
    assert persisted.execution_references.workflow_run_id == raised.value.run_id
    assert raised.value.state.agent_run_id is not None
    assert persisted.execution_references.agent_run_id == raised.value.state.agent_run_id


@pytest.mark.asyncio
async def test_repeated_cancellation_drains_turn_terminal_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_entered = asyncio.Event()

    class BlockingDriver:
        async def request(self, request: ModelRequest) -> object:
            model_entered.set()
            await asyncio.Future()

    harness = make_harness(
        tmp_path,
        binding=ModelDriverBinding.shared(
            descriptor=scripted_descriptor(),
            driver=BlockingDriver(),
        ),
    )
    terminal_entered = asyncio.Event()
    release_terminal = asyncio.Event()
    original_termination = type(harness.store).terminate_turn

    async def blocked_termination(*args: object, **kwargs: object):
        terminal_entered.set()
        await release_terminal.wait()
        return await original_termination(*args, **kwargs)

    monkeypatch.setattr(
        type(harness.store),
        "terminate_turn",
        blocked_termination,
    )
    turn = await harness.turns.admit(conversation_id="demo", text="Keep working")
    task = asyncio.create_task(harness.turns.execute(turn.id))
    await asyncio.wait_for(model_entered.wait(), timeout=0.2)

    task.cancel("first cancellation")
    await asyncio.wait_for(terminal_entered.wait(), timeout=0.2)
    task.cancel("second cancellation")
    release_terminal.set()
    with pytest.raises(WorkflowCancelledError, match="first cancellation"):
        await task

    persisted = await harness.store.get_turn(turn.id)
    assert persisted.status is TurnStatus.CANCELLED
    assert persisted.execution_references.workflow_run_id is not None
