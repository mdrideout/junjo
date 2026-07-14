"""Canonical deterministic Horizon 2 acceptance scenarios one through eight."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from conftest import RecordingImageRenderer, make_harness, scripted_descriptor
from junjo import AgentLimits, ModelDriverBinding
from junjo.agent import (
    AgentLimitExceededError,
    AgentToolError,
    AgentToolInputValidationError,
    FinalOutputResponse,
    ToolCall,
    ToolCallsResponse,
)
from junjo.agent.testing import ScriptedModelDriver
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ai_chat.domain.models import ChatAgentOutput, ImageArtifact, MessageRole


@pytest.mark.asyncio
async def test_scenario_1_general_request_produces_and_persists_direct_response(
    tmp_path: Path,
) -> None:
    harness = make_harness(
        tmp_path,
        script=[FinalOutputResponse(output={"message": "A direct answer.", "image": None})],
    )

    result = await harness.turns.submit(conversation_id="demo", text="Hello")

    messages = await harness.store.list_messages("demo")
    assert [message.role for message in messages] == [MessageRole.USER, MessageRole.ASSISTANT]
    assert result.user_message == messages[0]
    assert result.assistant_message == messages[1]
    assert result.assistant_message.content == "A direct answer."
    assert result.workflow_run_id != result.agent_run_id
    assert harness.driver is not None
    assert len(harness.driver.requests) == 1
    assert harness.renderer.calls == []


@pytest.mark.asyncio
async def test_scenario_2_history_question_calls_scoped_read_only_query_tool(
    tmp_path: Path,
) -> None:
    harness = make_harness(
        tmp_path,
        script=[
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="history-call",
                        name="search_conversation_history",
                        arguments={"query": "project", "limit": 5},
                    )
                ]
            ),
            FinalOutputResponse(output={"message": "You mentioned the Junjo project.", "image": None}),
        ],
    )
    await harness.store.append_user_message(
        conversation_id="demo",
        turn_id="prior-turn",
        content="I started the Junjo project.",
    )
    await harness.store.append_assistant_message(
        conversation_id="demo",
        turn_id="prior-turn",
        output=ChatAgentOutput(message="That sounds useful."),
    )

    result = await harness.turns.submit(
        conversation_id="demo",
        text="What did I say about the project in our history?",
    )

    assert result.assistant_message.content == "You mentioned the Junjo project."
    assert harness.driver is not None
    assert len(harness.driver.requests) == 2
    second_messages = harness.driver.requests[1].to_json()["messages"]
    tool_results = [message for message in second_messages if message["type"] == "tool_result"]
    assert tool_results == [
        {
            "type": "tool_result",
            "callId": "history-call",
            "toolName": "search_conversation_history",
            "result": {
                "matches": [
                    {
                        "turn_id": "prior-turn",
                        "role": "user",
                        "content": "I started the Junjo project.",
                    }
                ]
            },
        }
    ]
    messages = await harness.store.list_messages("demo")
    assert len(messages) == 4
    assert harness.renderer.calls == []


@pytest.mark.asyncio
async def test_scenario_3_image_request_calls_fresh_structured_workflow_tool(
    tmp_path: Path,
) -> None:
    artifact = ImageArtifact(
        id="rendered-image",
        url="/api/images/rendered-image.svg",
        alt_text="Deterministic illustration: a lighthouse",
    )
    harness = make_harness(
        tmp_path,
        script=[
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="image-call",
                        name="create_image",
                        arguments={"prompt": "a lighthouse"},
                    )
                ]
            ),
            FinalOutputResponse(
                output={"message": "Here is the lighthouse.", "image": artifact.model_dump(mode="json")}
            ),
        ],
    )

    result = await harness.turns.submit(conversation_id="demo", text="Draw a lighthouse")

    assert result.assistant_message.image == artifact
    assert harness.renderer.calls == [("a lighthouse", "Deterministic illustration: a lighthouse")]
    assert harness.driver is not None
    assert len(harness.driver.requests) == 2
    tool_result = harness.driver.requests[1].to_json()["messages"][-1]
    assert tool_result["toolName"] == "create_image"
    assert tool_result["result"]["artifact"]["id"] == "rendered-image"


@pytest.mark.asyncio
async def test_scenario_4_malformed_tool_arguments_fail_before_tool_side_effect(
    tmp_path: Path,
) -> None:
    harness = make_harness(
        tmp_path,
        script=[
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="malformed-history",
                        name="search_conversation_history",
                        arguments={"limit": 0},
                    )
                ]
            )
        ],
    )

    with pytest.raises(AgentToolInputValidationError) as raised:
        await harness.turns.submit(conversation_id="demo", text="Search history")

    assert raised.value.tool_name == "search_conversation_history"
    assert raised.value.state.tool_call_admitted_count == 0
    assert raised.value.state.tool_call_started_count == 0
    messages = await harness.store.list_messages("demo")
    assert [message.role for message in messages] == [MessageRole.USER]
    assert harness.renderer.calls == []


class ImageRenderFailure(RuntimeError):
    pass


class FailingImageRenderer(RecordingImageRenderer):
    async def render(self, *, prompt: str, alt_text: str) -> ImageArtifact:
        self.calls.append((prompt, alt_text))
        raise ImageRenderFailure("image renderer failed")


@pytest.mark.asyncio
async def test_scenario_5_nested_workflow_failure_surfaces_at_tool_agent_and_outer_workflow(
    tmp_path: Path,
    span_exporter: InMemorySpanExporter,
) -> None:
    renderer = FailingImageRenderer()
    harness = make_harness(
        tmp_path,
        renderer=renderer,
        script=[
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="failing-image",
                        name="create_image",
                        arguments={"prompt": "failure"},
                    )
                ]
            )
        ],
    )

    with pytest.raises(AgentToolError) as raised:
        await harness.turns.submit(conversation_id="demo", text="Create a failing image")

    assert raised.value.tool_name == "create_image"
    assert isinstance(raised.value.__cause__, ImageRenderFailure)
    assert raised.value.state.tool_call_started_count == 1
    assert raised.value.state.tool_call_completed_count == 0
    messages = await harness.store.list_messages("demo")
    assert [message.role for message in messages] == [MessageRole.USER]

    spans = tuple(span_exporter.get_finished_spans())
    outer = _named_span(spans, "Chat Turn Workflow")
    execute_agent = _named_span(spans, "ExecuteAgentNode")
    agent = _named_span(spans, "AI Chat Agent")
    tool = _operation_span(spans, "tool")
    nested = _named_span(spans, "Create Chat Image Workflow")
    render_image = _named_span(spans, "RenderImageNode")
    for span in (render_image, nested, tool, agent, execute_agent, outer):
        assert span.status.status_code.name == "ERROR"
        assert span.attributes["error.type"]
    assert agent.attributes["junjo.agent.outcome"] == "failed"
    assert agent.attributes["junjo.agent.termination_reason"] == "tool_error"
    _assert_parent(execute_agent, outer)
    _assert_parent(agent, execute_agent)
    _assert_parent(tool, agent)
    _assert_parent(nested, tool)
    _assert_parent(render_image, nested)
    assert not any(span.name == "PersistResultNode" for span in spans)


@pytest.mark.asyncio
async def test_scenario_6_looping_model_is_stopped_before_next_model_operation(
    tmp_path: Path,
) -> None:
    harness = make_harness(
        tmp_path,
        limits=AgentLimits(model_requests=2, tool_calls=2),
        script=[
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="loop-1",
                        name="search_conversation_history",
                        arguments={"query": "nothing", "limit": 1},
                    )
                ]
            ),
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="loop-2",
                        name="search_conversation_history",
                        arguments={"query": "nothing", "limit": 1},
                    )
                ]
            ),
        ],
    )

    with pytest.raises(AgentLimitExceededError) as raised:
        await harness.turns.submit(conversation_id="demo", text="Loop")

    assert raised.value.limit_kind == "model_requests"
    assert raised.value.limit == 2
    assert raised.value.attempted_count == 3
    assert harness.driver is not None
    assert len(harness.driver.requests) == 2
    messages = await harness.store.list_messages("demo")
    assert [message.role for message in messages] == [MessageRole.USER]


class BlockingImageRenderer(RecordingImageRenderer):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def render(self, *, prompt: str, alt_text: str) -> ImageArtifact:
        self.calls.append((prompt, alt_text))
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_scenario_7_cancellation_drains_active_nested_workflow_and_propagates_unchanged(
    tmp_path: Path,
    span_exporter: InMemorySpanExporter,
) -> None:
    renderer = BlockingImageRenderer()
    harness = make_harness(
        tmp_path,
        renderer=renderer,
        script=[
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="blocking-image",
                        name="create_image",
                        arguments={"prompt": "wait forever"},
                    )
                ]
            )
        ],
    )
    task = asyncio.create_task(harness.turns.submit(conversation_id="demo", text="Draw and wait"))
    await asyncio.wait_for(renderer.started.wait(), timeout=2)

    task.cancel("test cancellation")
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=2)

    assert task.done()
    assert renderer.cancelled.is_set()
    messages = await harness.store.list_messages("demo")
    assert [message.role for message in messages] == [MessageRole.USER]

    spans = tuple(span_exporter.get_finished_spans())
    outer = _named_span(spans, "Chat Turn Workflow")
    execute_agent = _named_span(spans, "ExecuteAgentNode")
    agent = _named_span(spans, "AI Chat Agent")
    tool = _operation_span(spans, "tool")
    nested = _named_span(spans, "Create Chat Image Workflow")
    render_image = _named_span(spans, "RenderImageNode")
    for span in (render_image, nested, tool, agent, execute_agent, outer):
        assert span.attributes["junjo.cancelled"] is True
        assert span.status.status_code.name == "UNSET"
    assert agent.attributes["junjo.agent.outcome"] == "cancelled"
    assert agent.attributes["junjo.agent.termination_reason"] == "cancelled"
    _assert_parent(execute_agent, outer)
    _assert_parent(agent, execute_agent)
    _assert_parent(tool, agent)
    _assert_parent(nested, tool)
    _assert_parent(render_image, nested)
    assert not any(span.name == "PersistResultNode" for span in spans)


@pytest.mark.asyncio
async def test_scenario_8_concurrent_turns_share_definition_but_not_run_state(
    tmp_path: Path,
) -> None:
    drivers: list[ScriptedModelDriver] = []

    def driver_factory() -> ScriptedModelDriver:
        driver = ScriptedModelDriver([FinalOutputResponse(output={"message": "isolated response", "image": None})])
        drivers.append(driver)
        return driver

    binding = ModelDriverBinding.per_run(
        descriptor=scripted_descriptor(),
        factory=driver_factory,
    )
    harness = make_harness(tmp_path, binding=binding)

    first, second = await asyncio.gather(
        harness.turns.submit(conversation_id="demo", text="first input"),
        harness.turns.submit(conversation_id="demo", text="second input"),
    )

    assert first.agent_run_id != second.agent_run_id
    assert first.workflow_run_id != second.workflow_run_id
    assert first.user_message.turn_id != second.user_message.turn_id
    assert len(drivers) == 2
    captured_inputs = sorted(
        str(driver.requests[0].to_json()["messages"][-1]["input"]["message"]) for driver in drivers
    )
    assert captured_inputs == ["first input", "second input"]
    messages = await harness.store.list_messages("demo")
    assert len(messages) == 4
    assert {message.turn_id for message in messages} == {
        first.user_message.turn_id,
        second.user_message.turn_id,
    }


def _named_span(spans: tuple[ReadableSpan, ...], name: str) -> ReadableSpan:
    matches = [span for span in spans if span.name == name]
    assert len(matches) == 1
    return matches[0]


def _operation_span(
    spans: tuple[ReadableSpan, ...],
    operation_type: str,
) -> ReadableSpan:
    matches = [span for span in spans if span.attributes.get("junjo.agent.operation_type") == operation_type]
    assert len(matches) == 1
    return matches[0]


def _assert_parent(child: ReadableSpan, parent: ReadableSpan) -> None:
    assert child.parent is not None
    assert child.parent.span_id == parent.context.span_id
