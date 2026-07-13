import pytest

from junjo import BaseState, BaseStore, Edge, Graph, GraphValidationError, Node, Subflow, Workflow


class ValidationState(BaseState):
    pass


class ValidationStore(BaseStore[ValidationState]):
    pass


class StartNode(Node[ValidationStore]):
    async def service(self, store: ValidationStore) -> None:
        return


class IntermediateNode(Node[ValidationStore]):
    async def service(self, store: ValidationStore) -> None:
        return


class SinkNode(Node[ValidationStore]):
    async def service(self, store: ValidationStore) -> None:
        return


class DeadEndNode(Node[ValidationStore]):
    async def service(self, store: ValidationStore) -> None:
        return


class ExampleSubflow(Subflow[ValidationState, ValidationStore, ValidationState, ValidationStore]):
    async def pre_run_actions(
        self,
        parent_store: ValidationStore,
        subflow_store: ValidationStore,
    ) -> None:
        return

    async def post_run_actions(
        self,
        parent_store: ValidationStore,
        subflow_store: ValidationStore,
    ) -> None:
        return


def test_validate_accepts_graph_with_reachable_plural_sinks_and_ordered_branching() -> None:
    start = StartNode()
    approve = SinkNode()
    reject = SinkNode()
    graph = Graph(
        source=start,
        sinks=[approve, reject],
        edges=[
            Edge(tail=start, head=approve),
            Edge(tail=start, head=reject),
        ],
    )

    assert graph.validate() is None


def test_validate_allows_retry_loop_when_sink_is_still_reachable() -> None:
    start = StartNode()
    retry = IntermediateNode()
    sink = SinkNode()
    graph = Graph(
        source=start,
        sinks=[sink],
        edges=[
            Edge(tail=start, head=retry),
            Edge(tail=retry, head=start),
            Edge(tail=start, head=sink),
        ],
    )

    assert graph.validate() is None


def test_validate_rejects_sink_with_outgoing_edges() -> None:
    start = StartNode()
    sink = SinkNode()
    graph = Graph(
        source=start,
        sinks=[sink],
        edges=[
            Edge(tail=start, head=sink),
            Edge(tail=sink, head=start),
        ],
    )

    with pytest.raises(GraphValidationError, match="sink|outgoing"):
        graph.validate()


def test_validate_rejects_reachable_non_sink_dead_end() -> None:
    start = StartNode()
    dead_end = DeadEndNode()
    declared_sink = SinkNode()
    graph = Graph(
        source=start,
        sinks=[declared_sink],
        edges=[Edge(tail=start, head=dead_end)],
    )

    with pytest.raises(GraphValidationError, match="dead-end|non-sink|No resolved edges"):
        graph.validate()


def test_validate_rejects_unreachable_declared_sink() -> None:
    start = StartNode()
    reached_sink = SinkNode()
    unreachable_sink = SinkNode()
    graph = Graph(
        source=start,
        sinks=[reached_sink, unreachable_sink],
        edges=[Edge(tail=start, head=reached_sink)],
    )

    with pytest.raises(GraphValidationError, match="unreachable|sink"):
        graph.validate()


def test_validate_recurses_into_subflows() -> None:
    child_start = StartNode()
    child_dead_end = DeadEndNode()
    child_sink = SinkNode()
    invalid_subflow = ExampleSubflow(
        graph_factory=lambda: Graph(
            source=child_start,
            sinks=[child_sink],
            edges=[Edge(tail=child_start, head=child_dead_end)],
        ),
        store_factory=lambda: ValidationStore(initial_state=ValidationState()),
    )
    parent_graph = Graph(source=invalid_subflow, sinks=[invalid_subflow], edges=[])

    with pytest.raises(GraphValidationError):
        parent_graph.validate()


class TrackingState(BaseState):
    steps: list[str] = []


class TrackingStore(BaseStore[TrackingState]):
    async def append_step(self, step: str) -> None:
        state = await self.get_state()
        await self.set_state({"steps": [*state.steps, step]})


class TrackingStartNode(Node[TrackingStore]):
    async def service(self, store: TrackingStore) -> None:
        await store.append_step("start")


class TrackingDeadEndNode(Node[TrackingStore]):
    async def service(self, store: TrackingStore) -> None:
        await store.append_step("dead-end")


class TrackingSinkNode(Node[TrackingStore]):
    async def service(self, store: TrackingStore) -> None:
        await store.append_step("sink")


@pytest.mark.asyncio
async def test_workflow_execute_validates_graph_before_running_by_default() -> None:
    created_stores: list[TrackingStore] = []

    def create_store() -> TrackingStore:
        store = TrackingStore(initial_state=TrackingState())
        created_stores.append(store)
        return store

    start = TrackingStartNode()
    dead_end = TrackingDeadEndNode()
    declared_sink = TrackingSinkNode()
    workflow = Workflow[TrackingState, TrackingStore](
        graph_factory=lambda: Graph(
            source=start,
            sinks=[declared_sink],
            edges=[Edge(tail=start, head=dead_end)],
        ),
        store_factory=create_store,
    )

    with pytest.raises(GraphValidationError, match="dead-ends without an outgoing edge"):
        await workflow.execute()

    assert len(created_stores) == 0


@pytest.mark.asyncio
async def test_workflow_execute_can_disable_graph_validation_per_run() -> None:
    created_stores: list[TrackingStore] = []

    def create_store() -> TrackingStore:
        store = TrackingStore(initial_state=TrackingState())
        created_stores.append(store)
        return store

    start = TrackingStartNode()
    dead_end = TrackingDeadEndNode()
    declared_sink = TrackingSinkNode()
    workflow = Workflow[TrackingState, TrackingStore](
        graph_factory=lambda: Graph(
            source=start,
            sinks=[declared_sink],
            edges=[Edge(tail=start, head=dead_end)],
        ),
        store_factory=create_store,
    )

    with pytest.raises(GraphValidationError, match="No resolved edges"):
        await workflow.execute(validate_graph=False)

    assert len(created_stores) == 1
    assert (await created_stores[0].get_state()).steps == ["start", "dead-end"]


@pytest.mark.asyncio
async def test_workflow_execute_propagates_validate_graph_to_nested_subflows() -> None:
    child_start = StartNode()
    child_dead_end = DeadEndNode()
    child_sink = SinkNode()
    invalid_subflow = ExampleSubflow(
        graph_factory=lambda: Graph(
            source=child_start,
            sinks=[child_sink],
            edges=[Edge(tail=child_start, head=child_dead_end)],
        ),
        store_factory=lambda: ValidationStore(initial_state=ValidationState()),
    )
    workflow = Workflow[ValidationState, ValidationStore](
        graph_factory=lambda: Graph(
            source=invalid_subflow,
            sinks=[invalid_subflow],
            edges=[],
        ),
        store_factory=lambda: ValidationStore(initial_state=ValidationState()),
    )

    with pytest.raises(GraphValidationError, match="dead-ends without an outgoing edge"):
        await workflow.execute()

    with pytest.raises(GraphValidationError, match="No resolved edges"):
        await workflow.execute(validate_graph=False)
