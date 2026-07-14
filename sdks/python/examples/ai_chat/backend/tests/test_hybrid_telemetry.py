"""Canonical Horizon 2 scenario nine: complete hybrid evidence in memory."""

from __future__ import annotations

import json
from pathlib import Path

import jsonpatch
import pytest
from conftest import make_harness
from junjo.agent import FinalOutputResponse, ToolCall, ToolCallsResponse
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ai_chat.domain.models import ImageArtifact


@pytest.mark.asyncio
async def test_scenario_9_complete_hybrid_hierarchy_and_all_stores_replay_in_memory(
    tmp_path: Path,
    span_exporter: InMemorySpanExporter,
) -> None:
    artifact = ImageArtifact(
        id="rendered-image",
        url="/api/images/rendered-image.svg",
        alt_text="Deterministic illustration: telemetry lighthouse",
    )
    harness = make_harness(
        tmp_path,
        script=[
            ToolCallsResponse(
                tool_calls=[
                    ToolCall(
                        id="telemetry-image",
                        name="create_image",
                        arguments={"prompt": "telemetry lighthouse"},
                    )
                ]
            ),
            FinalOutputResponse(
                output={
                    "message": "Telemetry image complete.",
                    "image": artifact.model_dump(mode="json"),
                }
            ),
        ],
    )

    result = await harness.turns.submit(
        conversation_id="demo",
        text="Surprise me with a telemetry visual",
    )

    spans = tuple(span_exporter.get_finished_spans())
    outer = _named(spans, "Chat Turn Workflow")
    initial_data = _named(spans, "Load Turn Context")
    load_context = _named(spans, "LoadRecentContextNode")
    load_contact = _named(spans, "LoadContactNode")
    execute_agent = _named(spans, "CreateGeneralAgentResponseNode")
    persist_outcome = _named(spans, "PersistOutcomeNode")
    agent = _named(spans, "AI Chat Agent")
    tool = _operation(spans, "tool")
    nested = _named(spans, "Create Chat Image Workflow")
    prepare_image = _named(spans, "PrepareImagePromptNode")
    render_image = _named(spans, "RenderImageNode")
    model_operations = sorted(
        (span for span in spans if span.attributes.get("junjo.agent.operation_type") == "model_request"),
        key=lambda span: span.attributes["junjo.agent.operation.sequence"],
    )

    assert outer.attributes["junjo.span_type"] == "workflow"
    assert agent.attributes["junjo.span_type"] == "agent"
    assert nested.attributes["junjo.span_type"] == "workflow"
    assert _parent_id(initial_data) == outer.context.span_id
    assert _parent_id(load_context) == initial_data.context.span_id
    assert _parent_id(load_contact) == initial_data.context.span_id
    assert _parent_id(execute_agent) == outer.context.span_id
    assert _parent_id(persist_outcome) == outer.context.span_id
    assert _parent_id(agent) == execute_agent.context.span_id
    assert [_parent_id(span) for span in model_operations] == [
        agent.context.span_id,
        agent.context.span_id,
    ]
    assert _parent_id(tool) == agent.context.span_id
    assert _parent_id(nested) == tool.context.span_id
    assert _parent_id(prepare_image) == nested.context.span_id
    assert _parent_id(render_image) == nested.context.span_id

    assert agent.attributes["junjo.parent_executable_type"] == "node"
    assert (
        agent.attributes["junjo.parent_executable_runtime_id"]
        == execute_agent.attributes["junjo.executable_runtime_id"]
    )
    assert nested.attributes["junjo.parent_executable_type"] == "agent"
    assert nested.attributes["junjo.parent_executable_runtime_id"] == result.execution_references.agent_run_id
    assert [
        span.attributes["junjo.agent.operation.sequence"]
        for span in (*model_operations[:1], tool, *model_operations[1:])
    ] == [1, 2, 3]
    assert agent.attributes["junjo.agent.operation.count"] == 3

    correlated_owner_spans = [span for span in spans if span.attributes.get("junjo.span_type") is not None]
    assert correlated_owner_spans
    for span in correlated_owner_spans:
        assert span.attributes["junjo.correlation.type"] == "ai_chat.turn"
        assert span.attributes["junjo.correlation.id"] == result.id
    for span in model_operations:
        assert "junjo.correlation.type" not in span.attributes
        assert "junjo.correlation.id" not in span.attributes
    assert "junjo.correlation.type" not in tool.attributes
    assert "junjo.correlation.id" not in tool.attributes

    store_ids = {
        outer.attributes["junjo.workflow.store.id"],
        agent.attributes["junjo.agent.store.id"],
        nested.attributes["junjo.workflow.store.id"],
    }
    assert len(store_ids) == 3
    _assert_store_replay(spans, outer, "junjo.workflow", "junjo.workflow.store.id")
    _assert_store_replay(spans, agent, "junjo.agent", "junjo.agent.store.id")
    _assert_store_replay(spans, nested, "junjo.workflow", "junjo.workflow.store.id")


def _named(spans: tuple[ReadableSpan, ...], name: str) -> ReadableSpan:
    return next(span for span in spans if span.name == name)


def _operation(spans: tuple[ReadableSpan, ...], operation_type: str) -> ReadableSpan:
    return next(span for span in spans if span.attributes.get("junjo.agent.operation_type") == operation_type)


def _parent_id(span: ReadableSpan) -> int | None:
    return span.parent.span_id if span.parent is not None else None


def _assert_store_replay(
    spans: tuple[ReadableSpan, ...],
    owner: ReadableSpan,
    state_root: str,
    store_attribute: str,
) -> None:
    store_id = owner.attributes[store_attribute]
    state = json.loads(owner.attributes[f"{state_root}.state.start"])
    expected_end = json.loads(owner.attributes[f"{state_root}.state.end"])
    transitions = sorted(
        (
            event
            for span in spans
            for event in span.events
            if event.name == "set_state" and event.attributes.get("junjo.store.id") == store_id
        ),
        key=lambda event: event.attributes["junjo.store.transition.sequence"],
    )
    assert [event.attributes["junjo.store.transition.sequence"] for event in transitions] == list(
        range(1, owner.attributes["junjo.store.transition.count"] + 1)
    )
    revision = owner.attributes["junjo.store.revision.start"]
    for event in transitions:
        assert event.attributes["junjo.store.revision.before"] == revision
        revision = event.attributes["junjo.store.revision.after"]
        state = jsonpatch.JsonPatch(json.loads(event.attributes["junjo.state_json_patch"])).apply(state, in_place=False)
    assert revision == owner.attributes["junjo.store.revision.end"]
    assert state == expected_end
    assert owner.attributes["junjo.store.reconstructable"] is True
