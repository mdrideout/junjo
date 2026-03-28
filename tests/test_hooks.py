import builtins
import importlib

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from junjo import BaseState, BaseStore, Graph, Hooks, Node, RunConcurrent, Subflow, Workflow


class HookState(BaseState):
    steps: list[str] = []


class HookStore(BaseStore[HookState]):
    async def append_step(self, step: str) -> None:
        state = await self.get_state()
        await self.set_state({"steps": [*state.steps, step]})


class HookNode(Node[HookStore]):
    async def service(self, store: HookStore) -> None:
        await store.append_step(self.name)


class NoopNode(Node[HookStore]):
    async def service(self, store: HookStore) -> None:
        return None


class ExampleSubflow(Subflow[HookState, HookStore, HookState, HookStore]):
    async def pre_run_actions(self, parent_store: HookStore, subflow_store: HookStore) -> None:
        parent_state = await parent_store.get_state()
        await subflow_store.set_state({"steps": list(parent_state.steps)})

    async def post_run_actions(self, parent_store: HookStore, subflow_store: HookStore) -> None:
        child_state = await subflow_store.get_state()
        await parent_store.set_state({"steps": [*child_state.steps, "merged"]})


@pytest.fixture(autouse=True)
def suppress_prints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)


@pytest.fixture
def span_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(trace._TRACER_PROVIDER_SET_ONCE, "_done", True)

    return exporter


def create_simple_workflow(*, hooks: Hooks | None = None) -> Workflow[HookState, HookStore]:
    node = HookNode()
    return Workflow[HookState, HookStore](
        name="Hook Workflow",
        graph_factory=lambda: Graph(source=node, sinks=[node], edges=[]),
        store_factory=lambda: HookStore(initial_state=HookState()),
        hooks=hooks,
    )


@pytest.mark.asyncio
async def test_hooks_dispatch_in_order_and_unsubscribe() -> None:
    hooks = Hooks()
    calls: list[str] = []

    removed = hooks.on_workflow_started(lambda event: calls.append("removed"))
    removed()

    hooks.on_workflow_started(lambda event: calls.append("sync"))

    async def async_hook(event) -> None:
        calls.append("async")

    hooks.on_workflow_started(async_hook)
    hooks.on_workflow_started(lambda event: calls.append("last"))

    await create_simple_workflow(hooks=hooks).execute()

    assert calls == ["sync", "async", "last"]


@pytest.mark.asyncio
async def test_workflow_and_node_hooks_emit_expected_lifecycle_payloads() -> None:
    hooks = Hooks()
    seen: list[tuple[str, object]] = []

    hooks.on_workflow_started(lambda event: seen.append(("workflow_started", event)))
    hooks.on_node_started(lambda event: seen.append(("node_started", event)))
    hooks.on_node_completed(lambda event: seen.append(("node_completed", event)))
    hooks.on_workflow_completed(lambda event: seen.append(("workflow_completed", event)))

    workflow = create_simple_workflow(hooks=hooks)
    result = await workflow.execute()

    names = [name for name, _ in seen]
    assert names == [
        "workflow_started",
        "node_started",
        "node_completed",
        "workflow_completed",
    ]

    workflow_started = seen[0][1]
    node_started = seen[1][1]
    node_completed = seen[2][1]
    workflow_completed = seen[3][1]

    assert workflow_started.hook_name == "workflow_started"
    assert node_started.hook_name == "node_started"
    assert node_completed.hook_name == "node_completed"
    assert workflow_completed.hook_name == "workflow_completed"
    assert workflow_started.run_id == result.run_id
    assert node_started.run_id == result.run_id
    assert node_started.parent_definition_id == workflow.id
    assert node_completed.parent_definition_id == workflow.id
    assert workflow_completed.result == result
    assert workflow_completed.store_id == workflow_started.store_id


@pytest.mark.asyncio
async def test_subflow_and_run_concurrent_hooks_are_distinct() -> None:
    hooks = Hooks()
    seen: list[str] = []

    hooks.on_subflow_started(lambda event: seen.append("subflow_started"))
    hooks.on_subflow_completed(lambda event: seen.append("subflow_completed"))
    hooks.on_run_concurrent_started(lambda event: seen.append("run_concurrent_started"))
    hooks.on_run_concurrent_completed(lambda event: seen.append("run_concurrent_completed"))

    subflow_node = HookNode()
    subflow = ExampleSubflow(
        name="Child Subflow",
        graph_factory=lambda: Graph(source=subflow_node, sinks=[subflow_node], edges=[]),
        store_factory=lambda: HookStore(initial_state=HookState()),
        hooks=hooks,
    )

    def create_graph() -> Graph:
        run_concurrent = RunConcurrent(
            name="Parallel Work",
            items=[subflow, NoopNode()],
        )
        return Graph(source=run_concurrent, sinks=[run_concurrent], edges=[])

    workflow = Workflow[HookState, HookStore](
        name="Parent Workflow",
        graph_factory=create_graph,
        store_factory=lambda: HookStore(initial_state=HookState()),
        hooks=hooks,
    )

    await workflow.execute()

    assert seen == [
        "run_concurrent_started",
        "subflow_started",
        "subflow_completed",
        "run_concurrent_completed",
    ]


@pytest.mark.asyncio
async def test_terminal_hooks_run_after_span_close(
    span_exporter: InMemorySpanExporter,
) -> None:
    hooks = Hooks()
    seen_closed: list[bool] = []

    def on_completed(event) -> None:
        finished_span_ids = {
            format(span.context.span_id, "016x")
            for span in span_exporter.get_finished_spans()
        }
        seen_closed.append(event.span_id in finished_span_ids)

    hooks.on_workflow_completed(on_completed)

    await create_simple_workflow(hooks=hooks).execute()

    assert seen_closed == [True]


@pytest.mark.asyncio
async def test_on_state_changed_delivers_patch_and_detached_snapshot() -> None:
    hooks = Hooks()
    state_events = []

    def on_state_changed(event) -> None:
        event.state.steps.append("hook-mutated")
        state_events.append(event)

    hooks.on_state_changed(on_state_changed)

    result = await create_simple_workflow(hooks=hooks).execute()

    assert len(state_events) == 1
    event = state_events[0]
    assert event.hook_name == "state_changed"
    assert event.store_name == "HookStore"
    assert event.action_name == "append_step"
    assert event.patch != "{}"
    assert event.parent_definition_id == result.definition_id
    assert event.state.steps == ["HookNode", "hook-mutated"]
    assert result.state.steps == ["HookNode"]


@pytest.mark.asyncio
async def test_hook_failures_are_isolated_and_recorded(
    span_exporter: InMemorySpanExporter,
) -> None:
    hooks = Hooks()
    observed: list[str] = []

    def failing_hook(event) -> None:
        raise RuntimeError("bad hook")

    hooks.on_workflow_started(failing_hook)
    hooks.on_workflow_started(lambda event: observed.append("ran"))

    result = await create_simple_workflow(hooks=hooks).execute()

    assert observed == ["ran"]

    hook_error_spans = [
        span for span in span_exporter.get_finished_spans() if span.name == "junjo.hook_error"
    ]
    assert len(hook_error_spans) == 1

    hook_error_span = hook_error_spans[0]
    assert hook_error_span.attributes["junjo.hook.event"] == "workflow_started"
    assert hook_error_span.attributes["junjo.hook.error.type"] == "RuntimeError"
    assert hook_error_span.attributes["junjo.hook.error.message"] == "bad hook"
    assert hook_error_span.attributes["junjo.run_id"] == result.run_id
    assert hook_error_span.attributes["junjo.definition_id"] == result.definition_id


def test_old_hook_manager_module_is_removed() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("junjo.telemetry.hook_manager")
