import json

import pytest

from junjo import (
    BaseState,
    BaseStore,
    CompiledGraph,
    Edge,
    Graph,
    GraphCompilationError,
    Node,
    RunConcurrent,
    Subflow,
)


class ParentState(BaseState):
    pass


class ParentStore(BaseStore[ParentState]):
    pass


class ChildState(BaseState):
    pass


class ChildStore(BaseStore[ChildState]):
    pass


class StartNode(Node[ChildStore]):
    async def service(self, store: ChildStore) -> None:
        return


class MiddleNode(Node[ChildStore]):
    async def service(self, store: ChildStore) -> None:
        return


class EndNode(Node[ChildStore]):
    async def service(self, store: ChildStore) -> None:
        return


class ExampleSubflow(Subflow[ChildState, ChildStore, ParentState, ParentStore]):
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


def test_compile_returns_same_snapshot_for_repeated_calls_on_one_graph_instance() -> None:
    start = StartNode()
    end = EndNode()
    graph = Graph(
        source=start,
        sinks=[end],
        edges=[Edge(tail=start, head=end)],
    )

    first = graph.compile()
    second = graph.compile()

    assert first is second


def test_graph_edges_are_immutable_after_construction() -> None:
    start = StartNode()
    end = EndNode()
    graph = Graph(
        source=start,
        sinks=[end],
        edges=[Edge(tail=start, head=end)],
    )

    assert isinstance(graph.edges, tuple)

    with pytest.raises(AttributeError):
        graph.edges.append(Edge(tail=start, head=end))


def test_compile_cache_is_safe_because_graph_shape_cannot_mutate() -> None:
    start = StartNode()
    end = EndNode()
    graph = Graph(
        source=start,
        sinks=[end],
        edges=[Edge(tail=start, head=end)],
    )

    compiled = graph.compile()

    with pytest.raises(AttributeError):
        graph.edges.append(Edge(tail=start, head=end))

    assert graph.compile() is compiled
    assert len(graph.compile().compiled_edges) == 1


def test_compile_collects_source_sinks_nodes_and_edges() -> None:
    start = StartNode()
    middle = MiddleNode()
    approve = EndNode()
    reject = EndNode()
    graph = Graph(
        source=start,
        sinks=[approve, reject],
        edges=[
            Edge(tail=start, head=middle),
            Edge(tail=middle, head=approve),
            Edge(tail=middle, head=reject),
        ],
    )

    compiled = graph.compile()

    assert isinstance(compiled, CompiledGraph)
    assert compiled.source_node_runtime_id == start.id
    assert compiled.sink_node_runtime_ids == (approve.id, reject.id)
    assert {node.node_runtime_id for node in compiled.compiled_nodes} == {
        start.id,
        middle.id,
        approve.id,
        reject.id,
    }
    assert tuple(edge.tail_node_runtime_id for edge in compiled.compiled_edges) == (
        start.id,
        middle.id,
        middle.id,
    )
    assert tuple(edge.head_node_runtime_id for edge in compiled.compiled_edges) == (
        middle.id,
        approve.id,
        reject.id,
    )
    assert tuple(
        edge.edge_structural_id
        for edge in compiled.outgoing_compiled_edges_by_tail_runtime_id[start.id]
    ) == (
        compiled.compiled_edges[0].edge_structural_id,
    )
    assert tuple(
        edge.edge_structural_id
        for edge in compiled.outgoing_compiled_edges_by_tail_runtime_id[middle.id]
    ) == (
        compiled.compiled_edges[1].edge_structural_id,
        compiled.compiled_edges[2].edge_structural_id,
    )


def test_compile_preserves_multiple_same_tail_head_edges() -> None:
    start = StartNode()
    end = EndNode()
    graph = Graph(
        source=start,
        sinks=[end],
        edges=[
            Edge(tail=start, head=end),
            Edge(tail=start, head=end),
        ],
    )

    compiled = graph.compile()

    assert len(compiled.compiled_edges) == 2
    assert (
        compiled.compiled_edges[0].tail_node_runtime_id
        == compiled.compiled_edges[1].tail_node_runtime_id
        == start.id
    )
    assert (
        compiled.compiled_edges[0].head_node_runtime_id
        == compiled.compiled_edges[1].head_node_runtime_id
        == end.id
    )
    assert (
        compiled.compiled_edges[0].edge_structural_id
        != compiled.compiled_edges[1].edge_structural_id
    )
    assert tuple(
        edge.edge_structural_id
        for edge in compiled.outgoing_compiled_edges_by_tail_runtime_id[start.id]
    ) == (
        compiled.compiled_edges[0].edge_structural_id,
        compiled.compiled_edges[1].edge_structural_id,
    )


def test_compile_compiles_nested_subflow_once() -> None:
    graph_factory_calls = 0

    def create_child_graph() -> Graph:
        nonlocal graph_factory_calls
        graph_factory_calls += 1
        start = StartNode()
        end = EndNode()
        return Graph(
            source=start,
            sinks=[end],
            edges=[Edge(tail=start, head=end)],
        )

    subflow = ExampleSubflow(
        graph_factory=create_child_graph,
        store_factory=lambda: ChildStore(initial_state=ChildState()),
    )
    parent_graph = Graph(source=subflow, sinks=[subflow], edges=[])

    compiled = parent_graph.compile()
    subflow_node = compiled.compiled_nodes_by_runtime_id[subflow.id]

    assert graph_factory_calls == 1
    assert subflow_node.is_subflow is True
    assert subflow_node.compiled_subflow_graph is not None
    assert subflow_node.compiled_subflow_graph.source_node_runtime_id != ""


def test_validate_then_serialize_reuses_same_compiled_subflow_snapshot() -> None:
    graph_factory_calls = 0

    def create_child_graph() -> Graph:
        nonlocal graph_factory_calls
        graph_factory_calls += 1
        start = StartNode()
        end = EndNode()
        return Graph(
            source=start,
            sinks=[end],
            edges=[Edge(tail=start, head=end)],
        )

    subflow = ExampleSubflow(
        graph_factory=create_child_graph,
        store_factory=lambda: ChildStore(initial_state=ChildState()),
    )
    parent_graph = Graph(source=subflow, sinks=[subflow], edges=[])

    parent_graph.validate()
    serialized = json.loads(parent_graph.serialize_to_json_string())

    assert graph_factory_calls == 1
    subflow_node = next(node for node in serialized["nodes"] if node.get("isSubflow"))
    assert subflow_node["subflowSourceNodeRuntimeId"]


def test_compile_records_run_concurrent_child_ids() -> None:
    child_one = StartNode()
    child_two = EndNode()
    concurrent = RunConcurrent(name="fan-out", items=[child_one, child_two])
    end = EndNode()
    graph = Graph(
        source=concurrent,
        sinks=[end],
        edges=[Edge(tail=concurrent, head=end)],
    )

    compiled = graph.compile()
    concurrent_node = compiled.compiled_nodes_by_runtime_id[concurrent.id]

    assert concurrent_node.is_concurrent_subgraph is True
    assert concurrent_node.child_node_runtime_ids == (child_one.id, child_two.id)


def test_compile_raises_typed_error_for_recursive_subflow_definition() -> None:
    recursive_subflow: ExampleSubflow | None = None

    def create_recursive_graph() -> Graph:
        start = StartNode()
        assert recursive_subflow is not None
        return Graph(
            source=start,
            sinks=[recursive_subflow],
            edges=[Edge(tail=start, head=recursive_subflow)],
        )

    recursive_subflow = ExampleSubflow(
        graph_factory=create_recursive_graph,
        store_factory=lambda: ChildStore(initial_state=ChildState()),
    )
    parent_graph = Graph(
        source=recursive_subflow,
        sinks=[recursive_subflow],
        edges=[],
    )

    with pytest.raises(GraphCompilationError, match="Recursive subflow graph definition"):
        parent_graph.compile()


def test_compile_assigns_graph_node_and_edge_structural_ids() -> None:
    start = StartNode()
    end = EndNode()
    graph = Graph(
        source=start,
        sinks=[end],
        edges=[Edge(tail=start, head=end)],
    )

    compiled = graph.compile()

    assert compiled.graph_structural_id.startswith("graph_")
    assert all(
        node.node_structural_id.startswith("node_")
        for node in compiled.compiled_nodes
    )
    assert all(
        edge.edge_structural_id.startswith("edge_")
        for edge in compiled.compiled_edges
    )


def test_structural_ids_are_stable_across_repeated_factory_calls() -> None:
    def create_graph() -> Graph:
        start = StartNode()
        middle = MiddleNode()
        end = EndNode()
        return Graph(
            source=start,
            sinks=[end],
            edges=[
                Edge(tail=start, head=middle),
                Edge(tail=middle, head=end),
            ],
        )

    first = create_graph().compile()
    second = create_graph().compile()

    assert first.graph_structural_id == second.graph_structural_id
    assert first.source_node_runtime_id != second.source_node_runtime_id
    assert tuple(node.node_structural_id for node in first.compiled_nodes) == tuple(
        node.node_structural_id for node in second.compiled_nodes
    )
    assert tuple(edge.edge_structural_id for edge in first.compiled_edges) == tuple(
        edge.edge_structural_id for edge in second.compiled_edges
    )


def test_graph_structural_id_changes_when_graph_shape_changes() -> None:
    start_one = StartNode()
    middle_one = MiddleNode()
    end_one = EndNode()
    first_graph = Graph(
        source=start_one,
        sinks=[end_one],
        edges=[
            Edge(tail=start_one, head=middle_one),
            Edge(tail=middle_one, head=end_one),
        ],
    )

    start_two = StartNode()
    middle_two = MiddleNode()
    extra_two = MiddleNode()
    end_two = EndNode()
    second_graph = Graph(
        source=start_two,
        sinks=[end_two],
        edges=[
            Edge(tail=start_two, head=middle_two),
            Edge(tail=middle_two, head=extra_two),
            Edge(tail=extra_two, head=end_two),
        ],
    )

    assert first_graph.compile().graph_structural_id != second_graph.compile().graph_structural_id


def test_run_concurrent_node_structural_ids_are_stable_across_repeated_factory_calls() -> None:
    def create_graph() -> Graph:
        concurrent = RunConcurrent(
            name="fan-out",
            items=[StartNode(), EndNode()],
        )
        sink = EndNode()
        return Graph(
            source=concurrent,
            sinks=[sink],
            edges=[Edge(tail=concurrent, head=sink)],
        )

    first = create_graph().compile()
    second = create_graph().compile()

    first_concurrent_node = next(
        node for node in first.compiled_nodes if node.is_concurrent_subgraph
    )
    second_concurrent_node = next(
        node for node in second.compiled_nodes if node.is_concurrent_subgraph
    )

    assert first_concurrent_node.node_runtime_id != second_concurrent_node.node_runtime_id
    assert (
        first_concurrent_node.node_structural_id
        == second_concurrent_node.node_structural_id
    )
