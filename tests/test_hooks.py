import builtins
import importlib
import json

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
    return Workflow[HookState, HookStore](
        name="Hook Workflow",
        graph_factory=lambda: _create_single_node_graph(),
        store_factory=lambda: HookStore(initial_state=HookState()),
        hooks=hooks,
    )


def _create_single_node_graph() -> Graph:
    node = HookNode()
    return Graph(source=node, sinks=[node], edges=[])


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
    assert workflow_started.executable_definition_id == workflow.id
    assert workflow_started.executable_runtime_id == result.run_id
    assert workflow_started.executable_structural_id.startswith("graph_")
    assert (
        workflow_started.enclosing_graph_structural_id
        == workflow_started.executable_structural_id
    )
    assert workflow_started.parent_executable_runtime_id is None
    assert node_started.run_id == result.run_id
    assert node_started.executable_runtime_id != result.run_id
    assert node_started.executable_structural_id.startswith("node_")
    assert (
        node_started.enclosing_graph_structural_id
        == workflow_started.enclosing_graph_structural_id
    )
    assert node_started.parent_executable_definition_id == workflow.id
    assert node_completed.parent_executable_definition_id == workflow.id
    assert node_started.parent_executable_runtime_id == result.run_id
    assert (
        node_started.parent_executable_structural_id
        == workflow_started.executable_structural_id
    )
    assert node_completed.executable_structural_id == node_started.executable_structural_id
    assert workflow_completed.result == result
    assert workflow_completed.store_id == workflow_started.store_id


@pytest.mark.asyncio
async def test_subflow_and_run_concurrent_hooks_are_distinct() -> None:
    hooks = Hooks()
    seen: list[tuple[str, object]] = []
    runtime_ids: dict[str, str] = {}

    hooks.on_subflow_started(lambda event: seen.append(("subflow_started", event)))
    hooks.on_subflow_completed(lambda event: seen.append(("subflow_completed", event)))
    hooks.on_run_concurrent_started(
        lambda event: seen.append(("run_concurrent_started", event))
    )
    hooks.on_run_concurrent_completed(
        lambda event: seen.append(("run_concurrent_completed", event))
    )

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
        runtime_ids["run_concurrent"] = run_concurrent.id
        return Graph(source=run_concurrent, sinks=[run_concurrent], edges=[])

    workflow = Workflow[HookState, HookStore](
        name="Parent Workflow",
        graph_factory=create_graph,
        store_factory=lambda: HookStore(initial_state=HookState()),
        hooks=hooks,
    )

    await workflow.execute()

    assert [name for name, _ in seen] == [
        "run_concurrent_started",
        "subflow_started",
        "subflow_completed",
        "run_concurrent_completed",
    ]
    run_concurrent_started = seen[0][1]
    subflow_started = seen[1][1]

    assert run_concurrent_started.executable_runtime_id == runtime_ids["run_concurrent"]
    assert run_concurrent_started.executable_structural_id.startswith("node_")
    assert subflow_started.parent_executable_runtime_id == runtime_ids["run_concurrent"]
    assert (
        subflow_started.parent_executable_structural_id
        == run_concurrent_started.executable_structural_id
    )
    assert subflow_started.executable_runtime_id != runtime_ids["run_concurrent"]
    assert subflow_started.executable_structural_id.startswith("graph_")


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
    assert event.executable_definition_id != result.definition_id
    assert event.executable_definition_id == event.executable_runtime_id
    assert event.name == "HookNode"
    assert event.span_type == "node"
    assert event.store_name == "HookStore"
    assert event.action_name == "append_step"
    assert event.patch != "{}"
    assert event.parent_executable_definition_id == result.definition_id
    assert event.executable_runtime_id != result.run_id
    assert event.executable_structural_id.startswith("node_")
    assert event.enclosing_graph_structural_id.startswith("graph_")
    assert event.parent_executable_runtime_id == result.run_id
    assert event.parent_executable_structural_id == event.enclosing_graph_structural_id
    assert event.state.steps == ["HookNode", "hook-mutated"]
    assert result.state.steps == ["HookNode"]


@pytest.mark.asyncio
async def test_state_changed_in_run_concurrent_uses_active_child_node_identity() -> None:
    hooks = Hooks()
    state_events = []

    hooks.on_state_changed(lambda event: state_events.append(event))

    child_node = HookNode()

    def create_graph() -> Graph:
        concurrent = RunConcurrent(name="Parallel Work", items=[child_node])
        return Graph(source=concurrent, sinks=[concurrent], edges=[])

    workflow = Workflow[HookState, HookStore](
        name="Concurrent Workflow",
        graph_factory=create_graph,
        store_factory=lambda: HookStore(initial_state=HookState()),
        hooks=hooks,
    )

    await workflow.execute()

    assert len(state_events) == 1
    event = state_events[0]
    assert event.executable_definition_id == child_node.id
    assert event.name == child_node.name
    assert event.span_type == "node"
    assert event.executable_runtime_id == child_node.id
    assert event.executable_structural_id.startswith("node_")
    assert event.parent_executable_definition_id != workflow.id
    assert event.parent_executable_runtime_id != workflow.id
    assert event.parent_executable_structural_id is not None


@pytest.mark.asyncio
async def test_state_changed_in_subflow_uses_child_node_identity_and_subflow_parent() -> None:
    hooks = Hooks()
    state_events = []

    hooks.on_state_changed(lambda event: state_events.append(event))

    child_node = HookNode()
    subflow = ExampleSubflow(
        name="Child Subflow",
        graph_factory=lambda: Graph(source=child_node, sinks=[child_node], edges=[]),
        store_factory=lambda: HookStore(initial_state=HookState()),
        hooks=hooks,
    )

    def create_graph() -> Graph:
        return Graph(source=subflow, sinks=[subflow], edges=[])

    workflow = Workflow[HookState, HookStore](
        name="Parent Workflow",
        graph_factory=create_graph,
        store_factory=lambda: HookStore(initial_state=HookState()),
        hooks=hooks,
    )

    await workflow.execute()

    child_events = [
        event
        for event in state_events
        if event.executable_definition_id == child_node.id
    ]

    assert len(child_events) == 1
    event = child_events[0]
    assert event.name == child_node.name
    assert event.span_type == "node"
    assert event.executable_runtime_id == child_node.id
    assert event.executable_structural_id.startswith("node_")
    assert event.parent_executable_definition_id == subflow.id
    assert event.parent_executable_runtime_id != workflow.id
    assert event.parent_executable_structural_id is not None


@pytest.mark.asyncio
async def test_state_changed_identity_matches_active_node_span_attributes(
    span_exporter: InMemorySpanExporter,
) -> None:
    hooks = Hooks()
    state_events = []

    hooks.on_state_changed(lambda event: state_events.append(event))

    await create_simple_workflow(hooks=hooks).execute()

    spans = {span.name: span for span in span_exporter.get_finished_spans()}
    node_span = spans["HookNode"]
    event = state_events[0]

    assert event.executable_definition_id == node_span.attributes["junjo.executable_definition_id"]
    assert event.executable_runtime_id == node_span.attributes["junjo.executable_runtime_id"]
    assert event.executable_structural_id == node_span.attributes["junjo.executable_structural_id"]
    assert event.enclosing_graph_structural_id == node_span.attributes["junjo.enclosing_graph_structural_id"]


@pytest.mark.asyncio
async def test_spans_emit_explicit_runtime_and_structural_identity_attributes(
    span_exporter: InMemorySpanExporter,
) -> None:
    result = await create_simple_workflow().execute()

    spans = {span.name: span for span in span_exporter.get_finished_spans()}
    workflow_span = spans["Hook Workflow"]
    node_span = spans["HookNode"]

    assert "junjo.id" not in workflow_span.attributes
    assert "junjo.parent_id" not in workflow_span.attributes
    assert "junjo.id" not in node_span.attributes
    assert "junjo.parent_id" not in node_span.attributes
    assert "junjo.workflow.graph_structure" not in workflow_span.attributes
    assert "junjo.workflow.execution_graph_snapshot" in workflow_span.attributes

    assert workflow_span.attributes["junjo.executable_runtime_id"] == result.run_id
    assert (
        workflow_span.attributes["junjo.executable_structural_id"]
        == workflow_span.attributes["junjo.enclosing_graph_structural_id"]
    )
    assert str(workflow_span.attributes["junjo.executable_structural_id"]).startswith(
        "graph_"
    )

    assert node_span.attributes["junjo.executable_runtime_id"] != result.run_id
    assert str(node_span.attributes["junjo.executable_structural_id"]).startswith(
        "node_"
    )
    assert node_span.attributes["junjo.parent_executable_runtime_id"] == result.run_id
    assert (
        node_span.attributes["junjo.parent_executable_structural_id"]
        == workflow_span.attributes["junjo.executable_structural_id"]
    )
    assert (
        node_span.attributes["junjo.enclosing_graph_structural_id"]
        == workflow_span.attributes["junjo.enclosing_graph_structural_id"]
    )

    execution_graph_snapshot = json.loads(
        str(workflow_span.attributes["junjo.workflow.execution_graph_snapshot"])
    )
    assert execution_graph_snapshot["graphStructuralId"].startswith("graph_")
    assert execution_graph_snapshot["nodes"][0]["nodeRuntimeId"] == node_span.attributes[
        "junjo.executable_runtime_id"
    ]
    assert execution_graph_snapshot["nodes"][0]["nodeStructuralId"] == node_span.attributes[
        "junjo.executable_structural_id"
    ]


@pytest.mark.asyncio
async def test_same_workflow_definition_rotates_runtime_ids_but_preserves_structural_ids() -> None:
    hooks = Hooks()
    workflow_events = []
    node_events = []

    hooks.on_workflow_started(lambda event: workflow_events.append(event))
    hooks.on_node_started(lambda event: node_events.append(event))

    workflow = create_simple_workflow(hooks=hooks)

    first_result = await workflow.execute()
    second_result = await workflow.execute()

    assert first_result.run_id != second_result.run_id
    assert len(workflow_events) == 2
    assert len(node_events) == 2

    first_workflow_event = workflow_events[0]
    second_workflow_event = workflow_events[1]
    assert first_workflow_event.executable_runtime_id != second_workflow_event.executable_runtime_id
    assert (
        first_workflow_event.executable_structural_id
        == second_workflow_event.executable_structural_id
    )
    assert (
        first_workflow_event.enclosing_graph_structural_id
        == second_workflow_event.enclosing_graph_structural_id
    )

    first_node_event = node_events[0]
    second_node_event = node_events[1]
    assert first_node_event.executable_runtime_id != second_node_event.executable_runtime_id
    assert first_node_event.executable_structural_id == second_node_event.executable_structural_id
    assert (
        first_node_event.enclosing_graph_structural_id
        == second_node_event.enclosing_graph_structural_id
    )


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
    assert (
        hook_error_span.attributes["junjo.executable_definition_id"]
        == result.definition_id
    )
    assert "junjo.parent_executable_definition_id" not in hook_error_span.attributes
    assert hook_error_span.attributes["junjo.executable_runtime_id"] == result.run_id
    assert (
        hook_error_span.attributes["junjo.executable_structural_id"]
        == hook_error_span.attributes["junjo.enclosing_graph_structural_id"]
    )


def test_old_hook_manager_module_is_removed() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("junjo.telemetry.hook_manager")
