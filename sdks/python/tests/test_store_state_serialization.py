import json

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pydantic import Field, field_serializer

from junjo import BaseState, BaseStore, Graph, Hooks, Node, Workflow

FULL_PROMPT = "Original prompt that must remain complete in runtime state."
UPDATED_PROMPT = "Updated prompt that must remain complete in runtime state."
TRUNCATED_UPDATED_PROMPT = "Updated prom...[truncated]"


class TelemetrySerializedState(BaseState):
    prompt: str
    raw_api_key: str | None = Field(default=None, exclude=True)
    count: int = 0

    @field_serializer("prompt")
    def serialize_prompt_for_telemetry(self, value: str) -> str:
        if len(value) <= 12:
            return value
        return value[:12] + "...[truncated]"


class TelemetrySerializedStore(BaseStore[TelemetrySerializedState]):
    async def set_count(self, count: int) -> None:
        await self.set_state({"count": count})

    async def set_prompt(self, prompt: str) -> None:
        await self.set_state({"prompt": prompt})


class SetCountNode(Node[TelemetrySerializedStore]):
    async def service(self, store: TelemetrySerializedStore) -> None:
        await store.set_count(1)


@pytest.fixture
def span_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(trace._TRACER_PROVIDER_SET_ONCE, "_done", True)

    return exporter


def create_serialized_store() -> TelemetrySerializedStore:
    return TelemetrySerializedStore(
        initial_state=TelemetrySerializedState(
            prompt=FULL_PROMPT,
            raw_api_key="secret",
        )
    )


@pytest.mark.asyncio
async def test_set_state_preserves_fields_excluded_from_serialization() -> None:
    store = create_serialized_store()

    await store.set_count(1)

    state = await store.get_state()
    assert state.raw_api_key == "secret"
    assert state.prompt == FULL_PROMPT
    assert state.count == 1


@pytest.mark.asyncio
async def test_set_state_preserves_runtime_value_when_serializer_truncates_telemetry(
    span_exporter: InMemorySpanExporter,
) -> None:
    store = create_serialized_store()
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("state-update"):
        await store.set_prompt(UPDATED_PROMPT)

    span = span_exporter.get_finished_spans()[0]
    set_state_event = next(event for event in span.events if event.name == "set_state")
    patch = json.loads(str(set_state_event.attributes["junjo.state_json_patch"]))

    assert patch == [
        {
            "op": "replace",
            "path": "/prompt",
            "value": TRUNCATED_UPDATED_PROMPT,
        }
    ]
    assert UPDATED_PROMPT not in str(set_state_event.attributes["junjo.state_json_patch"])
    assert "raw_api_key" not in str(set_state_event.attributes["junjo.state_json_patch"])

    await store.set_count(1)

    state = await store.get_state()
    assert state.prompt == UPDATED_PROMPT
    assert state.raw_api_key == "secret"
    assert state.count == 1


@pytest.mark.asyncio
async def test_set_state_validation_failure_keeps_runtime_state_unchanged() -> None:
    store = create_serialized_store()

    with pytest.raises(ValueError):
        await store.set_state({"count": "not an integer"})

    state = await store.get_state()
    assert state.prompt == FULL_PROMPT
    assert state.raw_api_key == "secret"
    assert state.count == 0


@pytest.mark.asyncio
async def test_state_changed_hook_receives_full_runtime_state() -> None:
    hooks = Hooks()
    state_events = []
    node = SetCountNode()

    hooks.on_state_changed(lambda event: state_events.append(event))

    workflow = Workflow[TelemetrySerializedState, TelemetrySerializedStore](
        name="Telemetry Serialized Workflow",
        graph_factory=lambda: Graph(source=node, sinks=[node], edges=[]),
        store_factory=create_serialized_store,
        hooks=hooks,
    )

    result = await workflow.execute()

    assert len(state_events) == 1
    event = state_events[0]
    assert event.state.prompt == FULL_PROMPT
    assert event.state.raw_api_key == "secret"
    assert event.state.count == 1
    assert json.loads(event.patch) == [
        {"op": "replace", "path": "/count", "value": 1}
    ]
    assert result.state.prompt == FULL_PROMPT
    assert result.state.raw_api_key == "secret"
    assert result.state.count == 1
