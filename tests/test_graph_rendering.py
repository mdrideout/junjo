from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from junjo import BaseState, BaseStore, Edge, Graph, Node, RunConcurrent, Subflow


class ParentState(BaseState):
    pass


class ParentStore(BaseStore[ParentState]):
    pass


class ChildState(BaseState):
    pass


class ChildStore(BaseStore[ChildState]):
    pass


class StartNode(Node[ParentStore]):
    async def service(self, store: ParentStore) -> None:
        return


class EndNode(Node[ParentStore]):
    async def service(self, store: ParentStore) -> None:
        return


class ConcurrentWorkerA(Node[ParentStore]):
    async def service(self, store: ParentStore) -> None:
        return


class ConcurrentWorkerB(Node[ParentStore]):
    async def service(self, store: ParentStore) -> None:
        return


class ChildStartNode(Node[ChildStore]):
    async def service(self, store: ChildStore) -> None:
        return


class ChildEndNode(Node[ChildStore]):
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


def _create_child_graph() -> Graph:
    child_start = ChildStartNode()
    child_end = ChildEndNode()
    return Graph(
        source=child_start,
        sinks=[child_end],
        edges=[Edge(tail=child_start, head=child_end)],
    )


def create_render_graph(*, subflow_name: str = "Review Subflow") -> Graph:
    start = StartNode()
    concurrent = RunConcurrent(
        name="Concurrent Work",
        items=[ConcurrentWorkerA(), ConcurrentWorkerB()],
    )
    subflow = ExampleSubflow(
        name=subflow_name,
        graph_factory=_create_child_graph,
        store_factory=lambda: ChildStore(initial_state=ChildState()),
    )
    end = EndNode()
    return Graph(
        source=start,
        sinks=[end],
        edges=[
            Edge(tail=start, head=concurrent),
            Edge(tail=concurrent, head=subflow),
            Edge(tail=subflow, head=end),
        ],
    )


def test_to_dot_notation_does_not_call_serialize_to_json_string(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = create_render_graph()

    def raise_if_called() -> str:
        raise AssertionError("to_dot_notation should render from CompiledGraph")

    monkeypatch.setattr(graph, "serialize_to_json_string", raise_if_called)

    dot = graph.to_dot_notation()

    assert 'digraph "G"' in dot


def test_export_graphviz_assets_does_not_depend_on_serialized_graph_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    graph = create_render_graph(subflow_name="Approval Subflow")

    def raise_if_called() -> str:
        raise AssertionError(
            "export_graphviz_assets should not depend on serialized graph JSON"
        )

    def fake_run(args: list[str], check: bool) -> subprocess.CompletedProcess[None]:
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(graph, "serialize_to_json_string", raise_if_called)
    monkeypatch.setattr(subprocess, "run", fake_run)

    digraph_files = graph.export_graphviz_assets(out_dir=tmp_path / "graphviz")

    assert "G" in digraph_files
    assert (tmp_path / "graphviz" / "index.html").exists()
    html = (tmp_path / "graphviz" / "index.html").read_text(encoding="utf-8")
    assert "Overview" in html
    assert "Approval Subflow" in html


def test_identical_graph_shapes_produce_identical_dot_output() -> None:
    first_graph = create_render_graph()
    second_graph = create_render_graph()

    assert first_graph.to_dot_notation() == second_graph.to_dot_notation()


def test_to_dot_notation_uses_structural_ids_for_node_identifiers() -> None:
    start = StartNode()
    end = EndNode()
    graph = Graph(
        source=start,
        sinks=[end],
        edges=[Edge(tail=start, head=end)],
    )

    compiled = graph.compile()
    start_node = compiled.compiled_nodes_by_runtime_id[start.id]
    end_node = compiled.compiled_nodes_by_runtime_id[end.id]
    dot = graph.to_dot_notation()

    assert start_node.node_structural_id in dot
    assert end_node.node_structural_id in dot
    assert start.id not in dot
    assert end.id not in dot


def test_to_dot_notation_renders_run_concurrent_cluster_from_compiled_node_metadata() -> None:
    graph = create_render_graph()
    compiled = graph.compile()
    concurrent_node = next(
        node for node in compiled.compiled_nodes if node.is_concurrent_subgraph
    )
    child_nodes = [
        compiled.compiled_nodes_by_runtime_id[child_runtime_id]
        for child_runtime_id in concurrent_node.child_node_runtime_ids
    ]

    dot = graph.to_dot_notation()

    assert f'subgraph "cluster_{concurrent_node.node_structural_id}"' in dot
    for child_node in child_nodes:
        assert child_node.node_structural_id in dot


def test_to_dot_notation_renders_subflow_digraph_from_compiled_subflow_graph() -> None:
    graph = create_render_graph(subflow_name="Child Review")
    compiled = graph.compile()
    subflow_node = next(node for node in compiled.compiled_nodes if node.is_subflow)
    assert subflow_node.compiled_subflow_graph is not None

    dot = graph.to_dot_notation()

    assert (
        f'digraph "subflow_{subflow_node.node_structural_id}"' in dot
    )
    assert subflow_node.compiled_subflow_graph.graph_structural_id not in dot
    assert (
        subflow_node.compiled_subflow_graph.compiled_nodes[0].node_structural_id
        in dot
    )
