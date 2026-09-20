"""Application Store composition through the real Agent and Workflow lifecycles."""

import asyncio
import json

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from junjo import (
    Agent,
    BaseState,
    BaseStore,
    Graph,
    Hooks,
    ModelDriverBinding,
    ModelDriverDescriptor,
    Node,
    RunConcurrent,
    Tool,
    Workflow,
)
from junjo.agent import AgentRunContext, AgentToolError, FinalOutputResponse, ToolCall, ToolCallsResponse
from junjo.agent.testing import ScriptedModelDriver


class State(BaseState):
    findings: list[str] = []


class Store(BaseStore[State]):
    async def append(self, finding: str) -> None:
        state = await self.get_state()
        await self.set_state({"findings": [*state.findings, finding]})


class Request(BaseModel):
    value: str


class Record(Node[Store]):
    async def service(self, store: Store) -> None:
        await store.append("workflow")


def workflow(*, hooks=None, node_factory=Record, store_factory=lambda: Store(State())):
    def graph():
        node = node_factory()
        return Graph(source=node, sinks=[node], edges=[])

    return Workflow[State, Store](graph_factory=graph, store_factory=store_factory, hooks=hooks)


def agent(service, *, store_factory=None, hooks=None):
    tool = Tool[Request, Request, None, Store](
        name="work",
        description="Record work",
        input_type=Request,
        output_type=Request,
        shared_service=service,
    )
    return Agent[Request, Request, None, State, Store](
        key="application",
        name="Application Agent",
        instructions="Do the work",
        input_type=Request,
        output_type=Request,
        tools=[tool],
        store_factory=store_factory,
        hooks=hooks,
        model=ModelDriverBinding.per_run(
            descriptor=ModelDriverDescriptor(driver_key="scripted", provider="junjo", model="fixture"),
            factory=lambda: ScriptedModelDriver(
                [
                    ToolCallsResponse(tool_calls=[ToolCall(id="work-1", name="work", arguments={"value": "agent"})]),
                    FinalOutputResponse(output={"value": "done"}),
                ]
            ),
        ),
    )


@pytest.fixture
def spans(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(trace._TRACER_PROVIDER_SET_ONCE, "_done", True)
    return exporter


@pytest.mark.asyncio
async def test_factory_and_borrowed_store_and_detached_result(spans):
    created = []

    def factory():
        store = Store(State())
        created.append(store)
        return store

    async def service(input: Request, context: AgentRunContext[None, Store]) -> Request:
        await context.store.append(input.value)
        return input

    definition = agent(service, store_factory=factory)
    first, second = await asyncio.gather(
        *[definition.execute(Request(value="run"), dependencies=None) for _ in range(2)]
    )
    assert len(created) == 2 and created[0] is not created[1]
    assert first.application_state == second.application_state == State(findings=["agent"])
    borrowed = Store(State(findings=["before"]))
    result = await definition.execute(Request(value="run"), dependencies=None, store=borrowed)
    assert len(created) == 2
    assert result.application_store_id == borrowed.id
    await borrowed.append("after")
    assert result.application_state == State(findings=["before", "agent"])
    assert not borrowed._telemetry_evidence._transitions


@pytest.mark.asyncio
async def test_nested_workflow_and_direct_node_tool_restore_outer_context(spans):
    observed = []
    hooks = Hooks()
    hooks.on_state_changed(lambda event: observed.append(event))

    async def service(input: Request, context: AgentRunContext[None, Store]) -> Request:
        await Record().execute(context.store, context.definition_id)
        await workflow(hooks=hooks).execute(store=context.store)
        return input

    child = agent(service)

    class Outer(Node[Store]):
        async def service(self, store):
            await store.append("before")
            result = await child.execute(Request(value="run"), dependencies=None, store=store)
            assert result.application_state.findings == ["before", "workflow", "workflow"]
            await store.append("after")

    result = await workflow(hooks=hooks, node_factory=Outer).execute()
    assert result.state.findings == ["before", "workflow", "workflow", "after"]
    assert [event.name for event in observed] == ["Outer", "Record", "Outer"]
    assert observed[0].run_id == observed[2].run_id != observed[1].run_id
    owners = [span for span in spans.get_finished_spans() if span.attributes.get("junjo.span_type") == "workflow"]
    assert len({span.attributes["junjo.workflow.store.id"] for span in owners}) == 1
    nested = next(span for span in owners if span.attributes["junjo.store.transition.start"] > 0)
    assert nested.attributes["junjo.store.transition.start"] == 2
    assert nested.attributes["junjo.store.transition.end"] == 3
    assert json.loads(nested.attributes["junjo.workflow.state.start"])["findings"] == ["before", "workflow"]


@pytest.mark.asyncio
async def test_concurrent_borrowers_keep_their_own_boundaries_and_hook_dispatch(spans):
    entered = asyncio.Event()
    proceed = asyncio.Event()
    hooks = Hooks()
    events = []
    hooks.on_state_changed(events.append)

    class Waiting(Node[Store]):
        async def service(self, store):
            await store.append("first")
            entered.set()
            await proceed.wait()
            await store.append("last")

    store = Store(State())
    await store.set_state({"findings": []})  # A no-op advances sequence, not revision.
    first = asyncio.create_task(workflow(hooks=hooks, node_factory=Waiting).execute(store=store))
    await entered.wait()
    second = await workflow(hooks=hooks).execute(store=store)
    proceed.set()
    await first
    assert second.state.findings == ["first", "workflow"]
    assert events[0].run_id == events[2].run_id != events[1].run_id
    owners = [s for s in spans.get_finished_spans() if s.attributes.get("junjo.span_type") == "workflow"]
    assert sorted(
        (s.attributes["junjo.store.transition.start"], s.attributes["junjo.store.transition.end"]) for s in owners
    ) == [(1, 4), (2, 3)]
    assert all(s.attributes["junjo.store.reconstructable"] for s in owners)
    assert not store._telemetry_evidence._boundaries and not store._telemetry_evidence._transitions


@pytest.mark.asyncio
async def test_run_concurrent_agents_share_application_store_and_keep_private_runtime(spans):
    ready = asyncio.Barrier(2)

    async def service(input, context):
        await ready.wait()
        await context.store.append(context.run_id)
        return input

    definition = agent(service)
    results = []

    class Invoke(Node[Store]):
        async def service(self, store):
            results.append(await definition.execute(Request(value="run"), dependencies=None, store=store))

    def graph():
        concurrent = RunConcurrent("Agents", [Invoke(), Invoke()])
        return Graph(source=concurrent, sinks=[concurrent], edges=[])

    store = Store(State())
    with trace.get_tracer(__name__).start_as_current_span("Shared application"):
        result = await Workflow(graph_factory=graph, store_factory=lambda: Store(State())).execute(store=store)
    assert set(result.state.findings) == {result.run_id for result in results}
    owners = [span for span in spans.get_finished_spans() if span.attributes.get("junjo.span_type") == "agent"]
    assert len({span.attributes["junjo.agent.store.id"] for span in owners}) == 2
    assert {span.attributes["junjo.agent.application_store.id"] for span in owners} == {store.id}
    assert all(span.attributes["junjo.agent.application_store.reconstructable"] for span in owners)
    assert not store._telemetry_evidence._boundaries and not store._telemetry_evidence._transitions


@pytest.mark.asyncio
async def test_failure_and_cancellation_leave_shared_state_available(spans):
    store = Store(State())
    ready = asyncio.Event()

    async def failing(input, context):
        await context.store.append("failed-work")
        raise ValueError("domain failure")

    with pytest.raises(AgentToolError) as captured:
        await agent(failing).execute(Request(value="run"), dependencies=None, store=store)
    assert captured.value.application_state == State(findings=["failed-work"])

    async def waiting(input, context):
        await context.store.append("cancelled-work")
        ready.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(agent(waiting).execute(Request(value="run"), dependencies=None, store=store))
    await ready.wait()
    survivor_ready = asyncio.Event()
    continue_survivor = asyncio.Event()

    class Survivor(Node[Store]):
        async def service(self, store):
            survivor_ready.set()
            await continue_survivor.wait()
            await store.append("workflow")

    survivor = asyncio.create_task(workflow(node_factory=Survivor).execute(store=store))
    await survivor_ready.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(store._telemetry_evidence._boundaries) == 1
    continue_survivor.set()
    result = await survivor
    assert result.state.findings == ["failed-work", "cancelled-work", "workflow"]
    assert not store._telemetry_evidence._boundaries
