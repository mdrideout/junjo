import builtins

import pytest

from junjo import (
    BaseState,
    BaseStore,
    Condition,
    Edge,
    Graph,
    GraphValidationError,
    Node,
    Subflow,
    Workflow,
)


class WorkflowState(BaseState):
    route: str
    steps: list[str] = []
    outcome: str | None = None


class WorkflowStore(BaseStore[WorkflowState]):
    async def append_step(self, step: str) -> None:
        state = await self.get_state()
        await self.set_state({"steps": [*state.steps, step]})

    async def set_outcome(self, outcome: str) -> None:
        await self.set_state({"outcome": outcome})


class RouteIs(Condition[WorkflowState]):
    def __init__(self, route: str):
        self.route = route

    def evaluate(self, state: WorkflowState) -> bool:
        return state.route == self.route


class CountingTrueCondition(Condition[WorkflowState]):
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, state: WorkflowState) -> bool:
        self.calls += 1
        return True


class StartNode(Node[WorkflowStore]):
    async def service(self, store: WorkflowStore) -> None:
        await store.append_step("start")


class ApproveNode(Node[WorkflowStore]):
    async def service(self, store: WorkflowStore) -> None:
        await store.append_step("approve")
        await store.set_outcome("approved")


class RejectNode(Node[WorkflowStore]):
    async def service(self, store: WorkflowStore) -> None:
        await store.append_step("reject")
        await store.set_outcome("rejected")


class OrphanTerminalNode(Node[WorkflowStore]):
    async def service(self, store: WorkflowStore) -> None:
        await store.append_step("orphan")
        await store.set_outcome("orphaned")


class ParentState(BaseState):
    route: str


class ParentStore(BaseStore[ParentState]):
    pass


class ChildState(BaseState):
    route: str = "approve"
    steps: list[str] = []
    outcome: str | None = None


class ChildStore(BaseStore[ChildState]):
    async def append_step(self, step: str) -> None:
        state = await self.get_state()
        await self.set_state({"steps": [*state.steps, step]})

    async def set_route(self, route: str) -> None:
        await self.set_state({"route": route})

    async def set_outcome(self, outcome: str) -> None:
        await self.set_state({"outcome": outcome})


class ChildRouteIs(Condition[ChildState]):
    def __init__(self, route: str):
        self.route = route

    def evaluate(self, state: ChildState) -> bool:
        return state.route == self.route


class ChildStartNode(Node[ChildStore]):
    async def service(self, store: ChildStore) -> None:
        await store.append_step("child_start")


class ChildApproveNode(Node[ChildStore]):
    async def service(self, store: ChildStore) -> None:
        await store.append_step("child_approve")
        await store.set_outcome("approved")


class ChildRejectNode(Node[ChildStore]):
    async def service(self, store: ChildStore) -> None:
        await store.append_step("child_reject")
        await store.set_outcome("rejected")


class ChildOrphanNode(Node[ChildStore]):
    async def service(self, store: ChildStore) -> None:
        await store.append_step("child_orphan")
        await store.set_outcome("orphaned")


class ExampleSubflow(Subflow[ChildState, ChildStore, ParentState, ParentStore]):
    async def pre_run_actions(
        self,
        parent_store: ParentStore,
        subflow_store: ChildStore,
    ) -> None:
        parent_state = await parent_store.get_state()
        await subflow_store.set_route(parent_state.route)

    async def post_run_actions(
        self,
        parent_store: ParentStore,
        subflow_store: ChildStore,
    ) -> None:
        return


@pytest.fixture(autouse=True)
def suppress_prints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)


@pytest.mark.parametrize(
    ("route", "expected_step", "expected_outcome"),
    [
        ("approve", "approve", "approved"),
        ("reject", "reject", "rejected"),
    ],
)
@pytest.mark.asyncio
async def test_workflow_terminates_successfully_on_any_declared_sink(
    route: str,
    expected_step: str,
    expected_outcome: str,
) -> None:
    start = StartNode()
    approve = ApproveNode()
    reject = RejectNode()
    workflow = Workflow[WorkflowState, WorkflowStore](
        graph_factory=lambda: Graph(
            source=start,
            sinks=[approve, reject],
            edges=[
                Edge(tail=start, head=approve, condition=RouteIs("approve")),
                Edge(tail=start, head=reject),
            ],
        ),
        store_factory=lambda: WorkflowStore(initial_state=WorkflowState(route=route)),
    )

    result = await workflow.execute()

    assert result.state.steps == ["start", expected_step]
    assert result.state.outcome == expected_outcome


@pytest.mark.asyncio
async def test_workflow_raises_when_dead_ending_on_node_not_in_sinks() -> None:
    start = StartNode()
    approve = ApproveNode()
    reject = RejectNode()
    orphan = OrphanTerminalNode()
    workflow = Workflow[WorkflowState, WorkflowStore](
        graph_factory=lambda: Graph(
            source=start,
            sinks=[approve, reject],
            edges=[Edge(tail=start, head=orphan)],
        ),
        store_factory=lambda: WorkflowStore(initial_state=WorkflowState(route="approve")),
    )

    with pytest.raises(GraphValidationError, match="dead-ends without an outgoing edge"):
        await workflow.execute()


@pytest.mark.asyncio
async def test_workflow_uses_first_matching_edge_in_declared_order_with_plural_sinks() -> None:
    start = StartNode()
    approve = ApproveNode()
    reject = RejectNode()
    first = CountingTrueCondition()
    second = CountingTrueCondition()

    workflow = Workflow[WorkflowState, WorkflowStore](
        graph_factory=lambda: Graph(
            source=start,
            sinks=[approve, reject],
            edges=[
                Edge(tail=start, head=approve, condition=first),
                Edge(tail=start, head=reject, condition=second),
            ],
        ),
        store_factory=lambda: WorkflowStore(initial_state=WorkflowState(route="approve")),
    )

    result = await workflow.execute()

    assert result.state.steps == ["start", "approve"]
    assert result.state.outcome == "approved"
    assert first.calls == 1
    assert second.calls == 0


@pytest.mark.parametrize(
    ("route", "expected_steps", "expected_outcome"),
    [
        ("approve", ["child_start", "child_approve"], "approved"),
        ("reject", ["child_start", "child_reject"], "rejected"),
    ],
)
@pytest.mark.asyncio
async def test_subflow_terminates_successfully_on_any_declared_sink(
    route: str,
    expected_steps: list[str],
    expected_outcome: str,
) -> None:
    def create_child_graph() -> Graph:
        child_start = ChildStartNode()
        child_approve = ChildApproveNode()
        child_reject = ChildRejectNode()
        return Graph(
            source=child_start,
            sinks=[child_approve, child_reject],
            edges=[
                Edge(
                    tail=child_start,
                    head=child_approve,
                    condition=ChildRouteIs("approve"),
                ),
                Edge(tail=child_start, head=child_reject),
            ],
        )

    subflow = ExampleSubflow(
        graph_factory=create_child_graph,
        store_factory=lambda: ChildStore(initial_state=ChildState()),
    )
    parent_store = ParentStore(initial_state=ParentState(route=route))

    result = await subflow.execute(parent_store=parent_store, parent_id="parent-id")

    assert result.state.steps == expected_steps
    assert result.state.outcome == expected_outcome


@pytest.mark.asyncio
async def test_subflow_raises_when_dead_ending_on_node_not_in_sinks() -> None:
    child_start = ChildStartNode()
    child_approve = ChildApproveNode()
    child_reject = ChildRejectNode()
    child_orphan = ChildOrphanNode()
    subflow = ExampleSubflow(
        graph_factory=lambda: Graph(
            source=child_start,
            sinks=[child_approve, child_reject],
            edges=[Edge(tail=child_start, head=child_orphan)],
        ),
        store_factory=lambda: ChildStore(initial_state=ChildState()),
    )
    parent_store = ParentStore(initial_state=ParentState(route="approve"))

    with pytest.raises(GraphValidationError, match="dead-ends without an outgoing edge"):
        await subflow.execute(parent_store=parent_store, parent_id="parent-id")


def test_graph_requires_sinks_argument() -> None:
    start = StartNode()

    with pytest.raises(TypeError):
        Graph(source=start, edges=[])  # type: ignore[call-arg]


def test_graph_rejects_removed_sink_argument() -> None:
    start = StartNode()
    end = ApproveNode()

    with pytest.raises(TypeError):
        Graph(source=start, sink=end, edges=[])  # type: ignore[call-arg]
