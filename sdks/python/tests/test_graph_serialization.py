import json
from unittest.mock import patch

import pytest

from junjo import (
    BaseState,
    BaseStore,
    Condition,
    Edge,
    Graph,
    GraphSerializationError,
    Node,
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


class EndNode(Node[ChildStore]):
    async def service(self, store: ChildStore) -> None:
        return


class AlwaysTrue(Condition[ChildState]):
    def evaluate(self, state: ChildState) -> bool:
        return True


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


def test_subflow_serialization_uses_one_graph_snapshot_per_pass() -> None:
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

    parent_graph.serialize_to_json_string()

    assert graph_factory_calls == 1


def test_subflow_serialization_source_and_sink_ids_exist_in_same_payload() -> None:
    def create_child_graph() -> Graph:
        start = StartNode()
        end = EndNode()
        alternate_end = EndNode()
        return Graph(
            source=start,
            sinks=[end, alternate_end],
            edges=[
                Edge(tail=start, head=end),
                Edge(tail=start, head=alternate_end),
            ],
        )

    subflow = ExampleSubflow(
        graph_factory=create_child_graph,
        store_factory=lambda: ChildStore(initial_state=ChildState()),
    )
    parent_graph = Graph(source=subflow, sinks=[subflow], edges=[])

    serialized = json.loads(parent_graph.serialize_to_json_string())
    nodes_by_id = {node["nodeRuntimeId"]: node for node in serialized["nodes"]}
    subflow_node = next(node for node in serialized["nodes"] if node.get("isSubflow"))

    assert subflow_node["subflowSourceNodeRuntimeId"] in nodes_by_id
    assert subflow_node["subflowSourceNodeStructuralId"].startswith("node_")
    assert len(subflow_node["subflowSinkNodeRuntimeIds"]) == 2
    assert len(subflow_node["subflowSinkNodeStructuralIds"]) == 2
    assert all(sink_id in nodes_by_id for sink_id in subflow_node["subflowSinkNodeRuntimeIds"])
    assert all(
        sink_structural_id.startswith("node_")
        for sink_structural_id in subflow_node["subflowSinkNodeStructuralIds"]
    )


def test_subflow_serialization_preserves_multiple_edges_with_same_tail_and_head() -> None:
    def create_child_graph() -> Graph:
        start = StartNode()
        end = EndNode()
        return Graph(
            source=start,
            sinks=[end],
            edges=[
                Edge(tail=start, head=end, condition=AlwaysTrue()),
                Edge(tail=start, head=end),
            ],
        )

    subflow = ExampleSubflow(
        graph_factory=create_child_graph,
        store_factory=lambda: ChildStore(initial_state=ChildState()),
    )
    parent_graph = Graph(source=subflow, sinks=[subflow], edges=[])

    serialized = json.loads(parent_graph.serialize_to_json_string())
    subflow_edges = [
        edge
        for edge in serialized["edges"]
        if edge["edgeScope"] == "subflow" and edge["parentSubflowRuntimeId"] == subflow.id
    ]

    assert len(subflow_edges) == 2
    assert len({edge["edgeStructuralId"] for edge in subflow_edges}) == 2


def test_serialize_to_json_string_raises_typed_error_for_json_encoding_failure() -> None:
    node = EndNode()
    graph = Graph(source=node, sinks=[node], edges=[])
    graph.compile()

    with patch.object(json, "dumps", side_effect=TypeError("boom")):
        with pytest.raises(GraphSerializationError, match="Failed to serialize graph to JSON"):
            graph.serialize_to_json_string()


def test_serialized_graph_includes_explicit_runtime_and_structural_identity_fields() -> None:
    start = StartNode()
    end = EndNode()
    graph = Graph(
        source=start,
        sinks=[end],
        edges=[Edge(tail=start, head=end)],
    )

    serialized = json.loads(graph.serialize_to_json_string())

    assert serialized["graphStructuralId"].startswith("graph_")
    assert serialized["nodes"][0]["nodeRuntimeId"]
    assert serialized["nodes"][0]["nodeStructuralId"].startswith("node_")
    assert serialized["edges"][0]["edgeStructuralId"].startswith("edge_")
    assert serialized["edges"][0]["tailNodeRuntimeId"] == start.id
    assert serialized["edges"][0]["headNodeRuntimeId"] == end.id
