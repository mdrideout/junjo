from __future__ import annotations

import json

import pytest
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import field_serializer

from junjo import BaseState, BaseStore, Edge, Graph, Node, Workflow


class State(BaseState):
    visible: int = 0
    hidden_projection: int = 0

    @field_serializer("hidden_projection")
    def serialize_hidden_projection(self, value: int) -> str:
        return "constant-projection"


class Store(BaseStore[State]):
    async def record_noop(self) -> None:
        state = await self.get_state()
        await self.set_state({"visible": state.visible})

    async def change_hidden_projection(self) -> None:
        state = await self.get_state()
        await self.set_state({"hidden_projection": state.hidden_projection + 1})


class NoopNode(Node[Store]):
    async def service(self, store: Store) -> None:
        await store.record_noop()


class HiddenChangeNode(Node[Store]):
    async def service(self, store: Store) -> None:
        await store.change_hidden_projection()


class DirectStateUpdateNode(Node[Store]):
    async def service(self, store: Store) -> None:
        await store.set_state({"visible": 1})


class PortableState(BaseState):
    value: int | str = 0


class PortableStore(BaseStore[PortableState]):
    async def set_value(self, value: int | str) -> None:
        await self.set_state({"value": value})


class DepthState(BaseState):
    value: object = None


class DepthStore(BaseStore[DepthState]):
    async def set_value(self, value: object) -> None:
        await self.set_state({"value": value})


def nested_arrays(depth: int) -> object:
    value: object = "leaf"
    for _ in range(depth):
        value = [value]
    return value


class SetPortableMaximumNode(Node[PortableStore]):
    async def service(self, store: PortableStore) -> None:
        await store.set_value(9_007_199_254_740_991)


@pytest.fixture
def span_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(trace._TRACER_PROVIDER_SET_ONCE, "_done", True)
    return exporter


def workflow_for(node_type: type[Node]) -> Workflow:
    def graph_factory() -> Graph:
        node = node_type()
        return Graph(source=node, sinks=[node], edges=[])

    return Workflow(
        name=f"{node_type.__name__} Workflow",
        graph_factory=graph_factory,
        store_factory=lambda: Store(State()),
    )


@pytest.mark.asyncio
async def test_true_noop_is_an_ordered_empty_patch_without_revision_increment(
    span_exporter: InMemorySpanExporter,
) -> None:
    await workflow_for(NoopNode).execute()

    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "workflow")
    event = next(event for span in spans for event in span.events if event.name == "set_state")
    assert owner.attributes["junjo.store.revision.start"] == 0
    assert owner.attributes["junjo.store.revision.end"] == 0
    assert owner.attributes["junjo.store.transition.count"] == 1
    assert owner.attributes["junjo.store.reconstructable"] is True
    assert event.attributes["junjo.store.transition.sequence"] == 1
    assert event.attributes["junjo.store.revision.before"] == 0
    assert event.attributes["junjo.store.revision.after"] == 0
    assert json.loads(event.attributes["junjo.state_json_patch"]) == []
    assert event.attributes["junjo.state_json_patch.mode"] == "full"
    assert event.attributes["junjo.state_json_patch.policy"] == "junjo.full.v1"


@pytest.mark.asyncio
async def test_live_change_hidden_by_projection_still_increments_revision_and_reconstructs(
    span_exporter: InMemorySpanExporter,
) -> None:
    result = await workflow_for(HiddenChangeNode).execute()

    spans = span_exporter.get_finished_spans()
    owner = next(span for span in spans if span.attributes.get("junjo.span_type") == "workflow")
    event = next(event for span in spans for event in span.events if event.name == "set_state")
    assert result.state.hidden_projection == 1
    assert owner.attributes["junjo.store.revision.end"] == 1
    assert owner.attributes["junjo.store.transition.count"] == 1
    assert owner.attributes["junjo.store.reconstructable"] is True
    assert json.loads(owner.attributes["junjo.workflow.state.start"]) == json.loads(
        owner.attributes["junjo.workflow.state.end"]
    )
    assert event.attributes["junjo.store.revision.before"] == 0
    assert event.attributes["junjo.store.revision.after"] == 1
    assert json.loads(event.attributes["junjo.state_json_patch"]) == []


@pytest.mark.asyncio
async def test_store_name_is_stable_across_distinct_public_callers(
    span_exporter: InMemorySpanExporter,
) -> None:
    def graph_factory() -> Graph:
        store_action = NoopNode()
        direct_action = DirectStateUpdateNode()
        return Graph(
            source=store_action,
            sinks=[direct_action],
            edges=[Edge(tail=store_action, head=direct_action)],
        )

    workflow = Workflow(
        name="Stable Store Name Workflow",
        graph_factory=graph_factory,
        store_factory=lambda: Store(State()),
    )

    result = await workflow.execute()

    events = sorted(
        (event for span in span_exporter.get_finished_spans() for event in span.events if event.name == "set_state"),
        key=lambda event: event.attributes["junjo.store.transition.sequence"],
    )
    assert result.state.visible == 1
    assert [event.attributes["junjo.store.name"] for event in events] == [
        "Store",
        "Store",
    ]
    assert [event.attributes["junjo.store.action"] for event in events] == [
        "record_noop",
        "service",
    ]
    assert len({event.attributes["junjo.store.id"] for event in events}) == 1


@pytest.mark.parametrize("value", [9_007_199_254_740_992, -9_007_199_254_740_992, "\ud800"])
def test_store_rejects_nonportable_initial_projection(value: int | str) -> None:
    with pytest.raises(ValueError):
        PortableStore(PortableState(value=value))


@pytest.mark.parametrize("value", [9_007_199_254_740_992, -9_007_199_254_740_992, "\ud800"])
@pytest.mark.asyncio
async def test_store_rejects_nonportable_update_before_live_or_evidence_commit(
    value: int | str,
) -> None:
    store = PortableStore(PortableState(value=7))

    with pytest.raises(ValueError):
        await store.set_value(value)

    assert (await store.get_state()).value == 7
    evidence = await store._get_store_owner_evidence()
    assert evidence.revision_end == 0
    assert evidence.transition_count == 0
    assert evidence.reconstructable is True


def test_store_initial_state_accepts_complete_depth_128_and_rejects_129() -> None:
    store = DepthStore(DepthState(value=nested_arrays(127)))
    assert store._get_initial_store_owner_evidence().state_start["value"] == (nested_arrays(127))

    with pytest.raises(ValueError):
        DepthStore(DepthState(value=nested_arrays(128)))
    with pytest.raises(ValueError):
        DepthStore(DepthState(value=nested_arrays(10_000)))


@pytest.mark.asyncio
async def test_store_update_rejects_over_depth_patch_before_state_or_evidence_commit() -> None:
    store = DepthStore(DepthState(value="before"))

    await store.set_value(nested_arrays(126))
    assert (await store.get_state()).value == nested_arrays(126)

    fresh_store = DepthStore(DepthState(value="before"))
    with pytest.raises(ValueError):
        await fresh_store.set_value(nested_arrays(127))
    with pytest.raises(ValueError):
        await fresh_store.set_value(nested_arrays(10_000))

    assert (await fresh_store.get_state()).value == "before"
    evidence = await fresh_store._get_store_owner_evidence()
    assert evidence.revision_end == 0
    assert evidence.transition_count == 0
    assert evidence.reconstructable is True


@pytest.mark.asyncio
async def test_workflow_store_portable_integer_limit_survives_otlp_encoding(
    span_exporter: InMemorySpanExporter,
) -> None:
    def graph_factory() -> Graph:
        node = SetPortableMaximumNode()
        return Graph(source=node, sinks=[node], edges=[])

    workflow = Workflow(
        name="Portable Workflow",
        graph_factory=graph_factory,
        store_factory=lambda: PortableStore(PortableState()),
    )

    result = await workflow.execute()

    assert result.state.value == 9_007_199_254_740_991
    owner = next(
        span for span in span_exporter.get_finished_spans() if span.attributes.get("junjo.span_type") == "workflow"
    )
    assert json.loads(owner.attributes["junjo.workflow.state.end"])["value"] == (9_007_199_254_740_991)
    encoded = encode_spans(span_exporter.get_finished_spans())
    assert encoded.SerializeToString()
