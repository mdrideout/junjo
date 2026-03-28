import asyncio
import builtins

import pytest

from junjo import BaseState, BaseStore, Edge, Graph, Node, RunConcurrent, Subflow, Workflow


class RuntimeState(BaseState):
    pass


class RuntimeStore(BaseStore[RuntimeState]):
    pass


class SlowStartNode(Node[RuntimeStore]):
    async def service(self, store: RuntimeStore) -> None:
        await asyncio.sleep(0.05)


class FastFinalNode(Node[RuntimeStore]):
    async def service(self, store: RuntimeStore) -> None:
        return


def create_reentrant_graph() -> Graph:
    first = SlowStartNode()
    final = FastFinalNode()
    return Graph(source=first, sinks=[final], edges=[Edge(tail=first, head=final)])


@pytest.mark.asyncio
async def test_same_workflow_instance_can_be_reentered_without_state_corruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)

    workflow = Workflow[RuntimeState, RuntimeStore](
        graph_factory=create_reentrant_graph,
        store_factory=lambda: RuntimeStore(initial_state=RuntimeState()),
    )

    first = asyncio.create_task(workflow.execute())
    await asyncio.sleep(0.01)
    second = asyncio.create_task(workflow.execute())

    results = await asyncio.gather(first, second, return_exceptions=True)
    exceptions = [result for result in results if isinstance(result, BaseException)]

    assert exceptions == []


class HookParentState(BaseState):
    label: str
    result: str | None = None


class HookParentStore(BaseStore[HookParentState]):
    async def set_result(self, result: str) -> None:
        await self.set_state({"result": result})


class HookChildState(BaseState):
    label: str | None = None


class HookChildStore(BaseStore[HookChildState]):
    async def set_label(self, label: str) -> None:
        await self.set_state({"label": label})


class SharedSlowChildNode(Node[HookChildStore]):
    async def service(self, store: HookChildStore) -> None:
        await asyncio.sleep(0.05)


SHARED_CHILD_NODE = SharedSlowChildNode()


def create_shared_single_node_subflow_graph() -> Graph:
    return Graph(source=SHARED_CHILD_NODE, sinks=[SHARED_CHILD_NODE], edges=[])


class HookLeakingSubflow(
    Subflow[HookChildState, HookChildStore, HookParentState, HookParentStore]
):
    async def pre_run_actions(
        self,
        parent_store: HookParentStore,
        subflow_store: HookChildStore,
    ) -> None:
        parent_state = await parent_store.get_state()
        await subflow_store.set_label(parent_state.label)

    async def post_run_actions(
        self,
        parent_store: HookParentStore,
        subflow_store: HookChildStore,
    ) -> None:
        child_state = await subflow_store.get_state()
        if child_state.label is None:
            raise ValueError("Subflow label is required.")
        await parent_store.set_result(child_state.label)


@pytest.mark.asyncio
async def test_same_subflow_instance_leaks_child_store_between_concurrent_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)

    subflow = HookLeakingSubflow(
        graph_factory=create_shared_single_node_subflow_graph,
        store_factory=lambda: HookChildStore(initial_state=HookChildState()),
    )
    parent_a = HookParentStore(initial_state=HookParentState(label="alpha"))
    parent_b = HookParentStore(initial_state=HookParentState(label="beta"))

    first = asyncio.create_task(subflow.execute(parent_a, "parent-a"))
    await asyncio.sleep(0.01)
    second = asyncio.create_task(subflow.execute(parent_b, "parent-b"))
    await asyncio.gather(first, second)

    assert (await parent_a.get_state()).result == "alpha"
    assert (await parent_b.get_state()).result == "beta"


class ParentState(BaseState):
    pass


class ParentStore(BaseStore[ParentState]):
    pass


class ChildState(BaseState):
    pass


class ChildStore(BaseStore[ChildState]):
    pass


class ParentNode(Node[ParentStore]):
    async def service(self, store: ParentStore) -> None:
        return


class ChildNode(Node[ChildStore]):
    async def service(self, store: ChildStore) -> None:
        await asyncio.sleep(0)


def create_child_graph() -> Graph:
    first = ChildNode()
    final = ChildNode()
    return Graph(source=first, sinks=[final], edges=[Edge(tail=first, head=final)])


class LoopingSubflow(Subflow[ChildState, ChildStore, ParentState, ParentStore]):
    async def pre_run_actions(
        self,
        parent_store: ParentStore,
        subflow_store: ChildStore,
    ) -> None:
        return

    async def post_run_actions(
        self,
        parent_store: ParentStore,
        subflow_store: ChildStore,
    ) -> None:
        return


def create_parent_graph_with_subflow_loop() -> Graph:
    subflow = LoopingSubflow(
        graph_factory=create_child_graph,
        store_factory=lambda: ChildStore(initial_state=ChildState()),
    )
    unreachable_sink = ParentNode()
    return Graph(
        source=subflow,
        sinks=[unreachable_sink],
        edges=[Edge(tail=subflow, head=subflow)],
    )


@pytest.mark.asyncio
async def test_subflow_loops_are_stopped_by_max_iterations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)

    workflow = Workflow[ParentState, ParentStore](
        graph_factory=create_parent_graph_with_subflow_loop,
        store_factory=lambda: ParentStore(initial_state=ParentState()),
        max_iterations=1,
    )

    with pytest.raises(ValueError, match="exceeded maximum execution count"):
        await asyncio.wait_for(workflow.execute(), timeout=0.1)


class ConcurrentState(BaseState):
    events: list[str] = []


class ConcurrentStore(BaseStore[ConcurrentState]):
    async def append_event(self, event: str) -> None:
        state = await self.get_state()
        await self.set_state({"events": [*state.events, event]})


@pytest.mark.asyncio
async def test_run_concurrent_cancels_siblings_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)

    sibling_started = asyncio.Event()
    failure_observed_by_caller = asyncio.Event()
    created_stores: list[ConcurrentStore] = []

    class WaitingSiblingNode(Node[ConcurrentStore]):
        async def service(self, store: ConcurrentStore) -> None:
            sibling_started.set()
            await failure_observed_by_caller.wait()
            await store.append_event("late-write")

    class FailingNode(Node[ConcurrentStore]):
        async def service(self, store: ConcurrentStore) -> None:
            await sibling_started.wait()
            await store.append_event("fail-start")
            raise RuntimeError("boom")

    def create_store() -> ConcurrentStore:
        store = ConcurrentStore(initial_state=ConcurrentState())
        created_stores.append(store)
        return store

    def create_run_concurrent_graph() -> Graph:
        run_concurrent = RunConcurrent(
            name="Concurrent Execution",
            items=[WaitingSiblingNode(), FailingNode()],
        )
        return Graph(source=run_concurrent, sinks=[run_concurrent], edges=[])

    workflow = Workflow[ConcurrentState, ConcurrentStore](
        graph_factory=create_run_concurrent_graph,
        store_factory=create_store,
    )

    with pytest.raises(RuntimeError, match="boom"):
        await workflow.execute()

    assert len(created_stores) == 1

    failure_observed_by_caller.set()
    await asyncio.sleep(0.05)

    current_state = await created_stores[0].get_state()

    assert current_state.events == ["fail-start"]
