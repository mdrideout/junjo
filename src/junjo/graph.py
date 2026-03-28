from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .edge import Edge
from .node import Node
from .run_concurrent import RunConcurrent
from .store import BaseStore
from .workflow import _NestableWorkflow


class GraphError(Exception):
    """Base class for graph-specific errors raised by Junjo."""


class GraphValidationError(GraphError, ValueError):
    """
    Raised when a graph shape or traversal outcome violates Junjo's graph
    rules.

    This includes invalid constructor inputs such as an empty ``sinks`` list
    and runtime traversal situations where execution dead-ends on a non-sink
    node.
    """


class GraphCompilationError(GraphError):
    """
    Raised when a graph cannot be compiled into a canonical structural form.

    Compilation failures are structural normalization failures, not traversal
    or validation failures. This exception is used when Junjo cannot produce a
    consistent compiled graph snapshot from the runtime graph definition.
    """


class GraphSerializationError(GraphError):
    """
    Raised when a graph cannot be converted into its serialized JSON form.

    This exception is used when Junjo successfully builds an in-memory graph
    payload, but ``json.dumps`` cannot serialize part of that payload. This is
    typically caused by attaching non-JSON-serializable values to graph-facing
    metadata such as node labels.
    """


class GraphRenderError(GraphError):
    """
    Raised when a graph cannot be rendered into an output format.

    This includes Graphviz command failures and unsupported rendering paths
    such as Mermaid output that Junjo has not implemented yet.
    """


@dataclass(frozen=True)
class CompiledEdge:
    """
    A normalized structural edge within a compiled graph snapshot.

    Compiled edges preserve the original declared ordering through
    ``edge_ordinal`` and keep a reference to the runtime :class:`~junjo.Edge`
    object so traversal can still evaluate conditions against the run-local
    store.
    """

    edge_structural_id: str
    edge_ordinal: int
    tail_node_runtime_id: str
    tail_node_structural_id: str
    head_node_runtime_id: str
    head_node_structural_id: str
    edge_condition_label: str | None
    edge_runtime_ref: Edge


@dataclass(frozen=True)
class CompiledNode:
    """
    A normalized structural node within a compiled graph snapshot.

    Compiled nodes capture the graph-facing metadata Junjo needs for
    validation, serialization, and rendering while preserving the original
    runtime node or subflow reference for execution-time operations.
    """

    node_runtime_id: str
    node_structural_id: str
    node_type_name: str
    node_label: str
    node_runtime_ref: Node | _NestableWorkflow
    is_concurrent_subgraph: bool = False
    is_subflow: bool = False
    child_node_runtime_ids: tuple[str, ...] = ()
    compiled_subflow_graph: CompiledGraph | None = None


@dataclass(frozen=True)
class CompiledGraph:
    """
    The canonical structural representation of a single :class:`~junjo.Graph`
    instance.

    A compiled graph is immutable and normalized for graph-facing features:

    - validation
    - traversal adjacency lookups
    - serialization
    - rendering

    Runtime graph objects still define the graph, but compiled snapshots are
    the single structural source of truth for all graph operations.
    """

    graph_structural_id: str
    source_node_runtime_id: str
    sink_node_runtime_ids: tuple[str, ...]
    compiled_nodes: tuple[CompiledNode, ...]
    compiled_nodes_by_runtime_id: Mapping[str, CompiledNode]
    compiled_edges: tuple[CompiledEdge, ...]
    outgoing_compiled_edges_by_tail_runtime_id: Mapping[str, tuple[CompiledEdge, ...]]
    reachable_node_runtime_ids: frozenset[str]


@dataclass(frozen=True)
class _CompiledNodeSeed:
    node_runtime_id: str
    node_type_name: str
    node_label: str
    node_runtime_ref: Node | _NestableWorkflow
    is_concurrent_subgraph: bool = False
    is_subflow: bool = False
    child_node_runtime_ids: tuple[str, ...] = ()
    compiled_subflow_graph: CompiledGraph | None = None


@dataclass(frozen=True)
class _CompiledEdgeSeed:
    edge_ordinal: int
    tail_node_runtime_id: str
    head_node_runtime_id: str
    edge_condition_label: str | None
    edge_runtime_ref: Edge


class Graph:
    """
    Represents a directed graph of nodes and edges, defining the structure and
    flow of a workflow.

    The ``Graph`` class is a fundamental component in Junjo, responsible for
    encapsulating the relationships between different processing units (Nodes
    or Subflows) and the conditions under which transitions between them occur.

    It holds references to the entry point (source) and explicit terminal
    nodes (sinks) of the graph, as well as a list of all edges that connect
    the nodes.

    :param source: The starting node or subflow of the graph. Execution of the workflow begins here.
    :type source: Node | _NestableWorkflow
    :param sinks: The explicit terminal nodes or subflows of the graph.
        Execution completes successfully only when one of these executables is
        reached.
    :type sinks: list[Node | _NestableWorkflow]
    :param edges: A list of :class:`~.Edge` instances that define the
        connections and transition logic between nodes in the graph.
    :type edges: list[Edge]

    .. rubric:: Example

    .. code-block:: python

        from junjo import Node, Edge, Graph, BaseStore, Condition, BaseState

        # Define a simple state (can be more complex in real scenarios)
        class MyWorkflowState(BaseState):
            count: int | None = None

        # Define a simple store
        class MyWorkflowStore(BaseStore[MyWorkflowState]):
            async def set_count(self, payload: int) -> None:
                await self.set_state({"count": payload})

        # Define some simple nodes
        class FirstNode(Node[MyWorkflowStore]):
            async def service(self, store: MyWorkflowStore) -> None:
                print("First Node Executed")

        class CountItemsNode(Node[MyWorkflowStore]):
            async def service(self, store: MyWorkflowStore) -> None:
                # In a real scenario, you might get items from state and count them
                await store.set_count(5) # Example count
                print("Counted items")

        class EvenItemsNode(Node[MyWorkflowStore]):
            async def service(self, store: MyWorkflowStore) -> None:
                print("Path taken for even items count.")

        class OddItemsNode(Node[MyWorkflowStore]):
            async def service(self, store: MyWorkflowStore) -> None:
                print("Path taken for odd items count.")

        class FinalNode(Node[MyWorkflowStore]):
            async def service(self, store: MyWorkflowStore) -> None:
                print("Final Node Executed")

        # Define a condition
        class CountIsEven(Condition[MyWorkflowState]):
            def evaluate(self, state: MyWorkflowState) -> bool:
                if state.count is None:
                    return False
                return state.count % 2 == 0

        # Instantiate the nodes
        first_node = FirstNode()
        count_items_node = CountItemsNode()
        even_items_node = EvenItemsNode()
        odd_items_node = OddItemsNode()
        final_node = FinalNode()

        # Create the workflow graph
        workflow_graph = Graph(
            source=first_node,
            sinks=[final_node],
            edges=[
                Edge(tail=first_node, head=count_items_node),
                Edge(tail=count_items_node, head=even_items_node, condition=CountIsEven()),
                Edge(tail=count_items_node, head=odd_items_node), # Fallback
                Edge(tail=even_items_node, head=final_node),
                Edge(tail=odd_items_node, head=final_node),
            ]
        )
    """
    def __init__(
        self,
        source: Node | _NestableWorkflow,
        sinks: list[Node | _NestableWorkflow],
        edges: list[Edge],
    ):
        if not sinks:
            raise GraphValidationError("Graph requires at least one sink.")
        self.source = source
        self.sinks = tuple(sinks)
        self.edges = edges
        self._compiled_graph: CompiledGraph | None = None

    @staticmethod
    def _node_label(node: Node | _NestableWorkflow) -> str:
        return str(
            getattr(node, "label", None)
            or getattr(node, "name", None)
            or node.__class__.__name__
        )

    @staticmethod
    def _hash_structural_descriptor(prefix: str, payload: dict) -> str:
        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(serialized).hexdigest()[:32]
        return f"{prefix}_{digest}"

    def _compile_subflow_graph(
        self,
        subflow: _NestableWorkflow,
        compiled_subflows: dict[str, CompiledGraph],
        active_subflows: set[str],
    ) -> CompiledGraph:
        if subflow.id in compiled_subflows:
            return compiled_subflows[subflow.id]
        if subflow.id in active_subflows:
            raise GraphCompilationError(
                f"Recursive subflow graph definition detected for '{subflow}'."
            )

        active_subflows.add(subflow.id)
        try:
            child_graph = subflow._graph_factory()
            compiled_graph = child_graph._compile(compiled_subflows, active_subflows)
            compiled_subflows[subflow.id] = compiled_graph
            return compiled_graph
        finally:
            active_subflows.discard(subflow.id)

    def _register_compiled_node_seed(
        self,
        node: Node | _NestableWorkflow,
        runtime_nodes_by_id: dict[str, Node | _NestableWorkflow],
        compiled_node_seeds_by_runtime_id: dict[str, _CompiledNodeSeed],
        compiled_subflows: dict[str, CompiledGraph],
        active_subflows: set[str],
    ) -> _CompiledNodeSeed:
        existing_runtime = runtime_nodes_by_id.get(node.id)
        if existing_runtime is not None and existing_runtime is not node:
            raise GraphCompilationError(
                f"Graph contains multiple runtime objects with the same id '{node.id}'."
            )
        existing_node = compiled_node_seeds_by_runtime_id.get(node.id)
        if existing_node is not None:
            return existing_node

        runtime_nodes_by_id[node.id] = node

        is_subgraph = isinstance(node, RunConcurrent)
        is_subflow = isinstance(node, _NestableWorkflow)
        child_item_ids = tuple(item.id for item in node.items) if is_subgraph else ()
        subflow_graph = (
            self._compile_subflow_graph(node, compiled_subflows, active_subflows)
            if is_subflow
            else None
        )

        compiled_node = _CompiledNodeSeed(
            node_runtime_id=node.id,
            node_type_name=node.__class__.__name__,
            node_label=self._node_label(node),
            node_runtime_ref=node,
            is_concurrent_subgraph=is_subgraph,
            is_subflow=is_subflow,
            child_node_runtime_ids=child_item_ids,
            compiled_subflow_graph=subflow_graph,
        )
        compiled_node_seeds_by_runtime_id[node.id] = compiled_node

        if is_subgraph:
            for item in node.items:
                self._register_compiled_node_seed(
                    item,
                    runtime_nodes_by_id,
                    compiled_node_seeds_by_runtime_id,
                    compiled_subflows,
                    active_subflows,
                )

        return compiled_node

    def _build_compiled_edge_seeds(
        self,
        runtime_nodes_by_id: dict[str, Node | _NestableWorkflow],
        compiled_node_seeds_by_runtime_id: dict[str, _CompiledNodeSeed],
        compiled_subflows: dict[str, CompiledGraph],
        active_subflows: set[str],
    ) -> list[_CompiledEdgeSeed]:
        compiled_edges: list[_CompiledEdgeSeed] = []
        for ordinal, edge in enumerate(self.edges):
            self._register_compiled_node_seed(
                edge.tail,
                runtime_nodes_by_id,
                compiled_node_seeds_by_runtime_id,
                compiled_subflows,
                active_subflows,
            )
            self._register_compiled_node_seed(
                edge.head,
                runtime_nodes_by_id,
                compiled_node_seeds_by_runtime_id,
                compiled_subflows,
                active_subflows,
            )
            compiled_edges.append(
                _CompiledEdgeSeed(
                    edge_ordinal=ordinal,
                    tail_node_runtime_id=edge.tail.id,
                    head_node_runtime_id=edge.head.id,
                    edge_condition_label=str(edge.condition) if edge.condition else None,
                    edge_runtime_ref=edge,
                )
            )
        return compiled_edges

    @staticmethod
    def _build_graph_structural_id(
        source_node_runtime_id: str,
        sink_node_runtime_ids: tuple[str, ...],
        compiled_node_seeds: list[_CompiledNodeSeed],
        compiled_edge_seeds: list[_CompiledEdgeSeed],
    ) -> str:
        node_ordinal_by_runtime_id = {
            node_seed.node_runtime_id: ordinal
            for ordinal, node_seed in enumerate(compiled_node_seeds)
        }
        descriptor = {
            "sourceNodeOrdinal": node_ordinal_by_runtime_id[source_node_runtime_id],
            "sinkNodeOrdinals": [
                node_ordinal_by_runtime_id[sink_runtime_id]
                for sink_runtime_id in sink_node_runtime_ids
            ],
            "nodes": [
                {
                    "nodeOrdinal": ordinal,
                    "nodeTypeName": node_seed.node_type_name,
                    "nodeLabel": node_seed.node_label,
                    "isConcurrentSubgraph": node_seed.is_concurrent_subgraph,
                    "isSubflow": node_seed.is_subflow,
                    "childNodeOrdinals": [
                        node_ordinal_by_runtime_id[child_runtime_id]
                        for child_runtime_id in node_seed.child_node_runtime_ids
                    ],
                    "subflowGraphStructuralId": (
                        node_seed.compiled_subflow_graph.graph_structural_id
                        if node_seed.compiled_subflow_graph is not None
                        else None
                    ),
                }
                for ordinal, node_seed in enumerate(compiled_node_seeds)
            ],
            "edges": [
                {
                    "edgeOrdinal": edge_seed.edge_ordinal,
                    "tailNodeOrdinal": node_ordinal_by_runtime_id[edge_seed.tail_node_runtime_id],
                    "headNodeOrdinal": node_ordinal_by_runtime_id[edge_seed.head_node_runtime_id],
                    "edgeConditionLabel": edge_seed.edge_condition_label,
                }
                for edge_seed in compiled_edge_seeds
            ],
        }
        return Graph._hash_structural_descriptor("graph", descriptor)

    @staticmethod
    def _build_compiled_nodes(
        graph_structural_id: str,
        compiled_node_seeds: list[_CompiledNodeSeed],
    ) -> list[CompiledNode]:
        compiled_nodes: list[CompiledNode] = []
        for ordinal, node_seed in enumerate(compiled_node_seeds):
            node_structural_id = Graph._hash_structural_descriptor(
                "node",
                {
                    "graphStructuralId": graph_structural_id,
                    "nodeOrdinal": ordinal,
                    "nodeTypeName": node_seed.node_type_name,
                    "nodeLabel": node_seed.node_label,
                    "isConcurrentSubgraph": node_seed.is_concurrent_subgraph,
                    "isSubflow": node_seed.is_subflow,
                    "childNodeRuntimeIds": list(node_seed.child_node_runtime_ids),
                    "subflowGraphStructuralId": (
                        node_seed.compiled_subflow_graph.graph_structural_id
                        if node_seed.compiled_subflow_graph is not None
                        else None
                    ),
                },
            )
            compiled_nodes.append(
                CompiledNode(
                    node_runtime_id=node_seed.node_runtime_id,
                    node_structural_id=node_structural_id,
                    node_type_name=node_seed.node_type_name,
                    node_label=node_seed.node_label,
                    node_runtime_ref=node_seed.node_runtime_ref,
                    is_concurrent_subgraph=node_seed.is_concurrent_subgraph,
                    is_subflow=node_seed.is_subflow,
                    child_node_runtime_ids=node_seed.child_node_runtime_ids,
                    compiled_subflow_graph=node_seed.compiled_subflow_graph,
                )
            )
        return compiled_nodes

    @staticmethod
    def _build_compiled_edges(
        graph_structural_id: str,
        compiled_node_seeds: list[_CompiledNodeSeed],
        compiled_nodes_by_runtime_id: Mapping[str, CompiledNode],
        compiled_edge_seeds: list[_CompiledEdgeSeed],
    ) -> list[CompiledEdge]:
        node_ordinal_by_runtime_id = {
            node_seed.node_runtime_id: ordinal
            for ordinal, node_seed in enumerate(compiled_node_seeds)
        }
        compiled_edges: list[CompiledEdge] = []
        for edge_seed in compiled_edge_seeds:
            tail_node = compiled_nodes_by_runtime_id[edge_seed.tail_node_runtime_id]
            head_node = compiled_nodes_by_runtime_id[edge_seed.head_node_runtime_id]
            edge_structural_id = Graph._hash_structural_descriptor(
                "edge",
                {
                    "graphStructuralId": graph_structural_id,
                    "edgeOrdinal": edge_seed.edge_ordinal,
                    "tailNodeOrdinal": node_ordinal_by_runtime_id[edge_seed.tail_node_runtime_id],
                    "headNodeOrdinal": node_ordinal_by_runtime_id[edge_seed.head_node_runtime_id],
                    "edgeConditionLabel": edge_seed.edge_condition_label,
                },
            )
            compiled_edges.append(
                CompiledEdge(
                    edge_structural_id=edge_structural_id,
                    edge_ordinal=edge_seed.edge_ordinal,
                    tail_node_runtime_id=edge_seed.tail_node_runtime_id,
                    tail_node_structural_id=tail_node.node_structural_id,
                    head_node_runtime_id=edge_seed.head_node_runtime_id,
                    head_node_structural_id=head_node.node_structural_id,
                    edge_condition_label=edge_seed.edge_condition_label,
                    edge_runtime_ref=edge_seed.edge_runtime_ref,
                )
            )
        return compiled_edges

    @staticmethod
    def _freeze_outgoing_compiled_edges(
        compiled_edges: list[CompiledEdge],
    ) -> Mapping[str, tuple[CompiledEdge, ...]]:
        outgoing_edge_map: dict[str, list[CompiledEdge]] = {}
        for edge in compiled_edges:
            outgoing_edge_map.setdefault(edge.tail_node_runtime_id, []).append(edge)
        return MappingProxyType(
            {
                node_id: tuple(edges)
                for node_id, edges in outgoing_edge_map.items()
            }
        )

    @staticmethod
    def _collect_reachable_node_runtime_ids(
        source_node_runtime_id: str,
        outgoing_compiled_edges_by_tail_runtime_id: Mapping[str, tuple[CompiledEdge, ...]],
    ) -> frozenset[str]:
        reachable_node_ids: set[str] = set()
        queue: list[str] = [source_node_runtime_id]
        while queue:
            current_id = queue.pop(0)
            if current_id in reachable_node_ids:
                continue
            reachable_node_ids.add(current_id)
            for edge in outgoing_compiled_edges_by_tail_runtime_id.get(current_id, ()):
                if edge.head_node_runtime_id not in reachable_node_ids:
                    queue.append(edge.head_node_runtime_id)
        return frozenset(reachable_node_ids)

    def _compile(
        self,
        compiled_subflows: dict[str, CompiledGraph],
        active_subflows: set[str],
    ) -> CompiledGraph:
        if self._compiled_graph is not None:
            return self._compiled_graph

        runtime_nodes_by_id: dict[str, Node | _NestableWorkflow] = {}
        compiled_node_seeds_by_runtime_id: dict[str, _CompiledNodeSeed] = {}

        self._register_compiled_node_seed(
            self.source,
            runtime_nodes_by_id,
            compiled_node_seeds_by_runtime_id,
            compiled_subflows,
            active_subflows,
        )
        for sink in self.sinks:
            self._register_compiled_node_seed(
                sink,
                runtime_nodes_by_id,
                compiled_node_seeds_by_runtime_id,
                compiled_subflows,
                active_subflows,
            )

        compiled_edge_seeds = self._build_compiled_edge_seeds(
            runtime_nodes_by_id,
            compiled_node_seeds_by_runtime_id,
            compiled_subflows,
            active_subflows,
        )
        compiled_node_seeds = list(compiled_node_seeds_by_runtime_id.values())
        graph_structural_id = self._build_graph_structural_id(
            self.source.id,
            tuple(sink.id for sink in self.sinks),
            compiled_node_seeds,
            compiled_edge_seeds,
        )
        compiled_nodes = self._build_compiled_nodes(
            graph_structural_id,
            compiled_node_seeds,
        )
        compiled_nodes_by_runtime_id = MappingProxyType(
            {
                compiled_node.node_runtime_id: compiled_node
                for compiled_node in compiled_nodes
            }
        )
        compiled_edges = self._build_compiled_edges(
            graph_structural_id,
            compiled_node_seeds,
            compiled_nodes_by_runtime_id,
            compiled_edge_seeds,
        )
        outgoing_compiled_edges_by_tail_runtime_id = self._freeze_outgoing_compiled_edges(
            compiled_edges
        )
        reachable_node_runtime_ids = self._collect_reachable_node_runtime_ids(
            self.source.id,
            outgoing_compiled_edges_by_tail_runtime_id,
        )

        compiled_graph = CompiledGraph(
            graph_structural_id=graph_structural_id,
            source_node_runtime_id=self.source.id,
            sink_node_runtime_ids=tuple(sink.id for sink in self.sinks),
            compiled_nodes=tuple(compiled_nodes),
            compiled_nodes_by_runtime_id=compiled_nodes_by_runtime_id,
            compiled_edges=tuple(compiled_edges),
            outgoing_compiled_edges_by_tail_runtime_id=outgoing_compiled_edges_by_tail_runtime_id,
            reachable_node_runtime_ids=reachable_node_runtime_ids,
        )
        self._compiled_graph = compiled_graph
        return compiled_graph

    def compile(self) -> CompiledGraph:
        """
        Compile this graph into one canonical structural snapshot.

        The compiled snapshot is cached per :class:`~junjo.Graph` instance and
        becomes the structural source of truth for validation, traversal, and
        serialization.

        Compiling a graph does not execute node logic or evaluate edge
        conditions. It only normalizes the graph structure into a single,
        immutable representation.

        :returns: The compiled structural snapshot for this graph instance.
        :rtype: CompiledGraph
        :raises GraphCompilationError: If Junjo cannot build a consistent
            structural representation of the graph.
        """
        return self._compile(compiled_subflows={}, active_subflows=set())

    @staticmethod
    def _validate_compiled_sinks_have_no_outgoing_edges(compiled: CompiledGraph) -> None:
        for sink_id in compiled.sink_node_runtime_ids:
            if compiled.outgoing_compiled_edges_by_tail_runtime_id.get(sink_id):
                sink_runtime = compiled.compiled_nodes_by_runtime_id[sink_id].node_runtime_ref
                raise GraphValidationError(
                    f"Declared sink '{sink_runtime}' has outgoing edges."
                )

    @staticmethod
    def _validate_compiled_reachable_non_sink_nodes(compiled: CompiledGraph) -> None:
        sink_ids = set(compiled.sink_node_runtime_ids)
        for node_id in compiled.reachable_node_runtime_ids:
            if node_id in sink_ids:
                continue
            if not compiled.outgoing_compiled_edges_by_tail_runtime_id.get(node_id):
                node_runtime = compiled.compiled_nodes_by_runtime_id[node_id].node_runtime_ref
                raise GraphValidationError(
                    "Reachable non-sink "
                    f"'{node_runtime}' dead-ends without an outgoing edge."
                )

    @staticmethod
    def _validate_compiled_declared_sinks_are_reachable(compiled: CompiledGraph) -> None:
        for sink_id in compiled.sink_node_runtime_ids:
            if sink_id not in compiled.reachable_node_runtime_ids:
                sink_runtime = compiled.compiled_nodes_by_runtime_id[sink_id].node_runtime_ref
                raise GraphValidationError(
                    f"Declared sink '{sink_runtime}' is unreachable from the source."
                )

    def _validate_compiled_nested_subflows(
        self,
        compiled: CompiledGraph,
        validated_subflows: set[str],
    ) -> None:
        for node in compiled.compiled_nodes:
            if not node.is_subflow or node.compiled_subflow_graph is None:
                continue
            if node.node_runtime_id in validated_subflows:
                continue
            validated_subflows.add(node.node_runtime_id)
            self._validate_compiled_graph(node.compiled_subflow_graph, validated_subflows)

    def _validate_compiled_graph(
        self,
        compiled: CompiledGraph,
        validated_subflows: set[str],
    ) -> None:
        self._validate_compiled_sinks_have_no_outgoing_edges(compiled)
        self._validate_compiled_reachable_non_sink_nodes(compiled)
        self._validate_compiled_declared_sinks_are_reachable(compiled)
        self._validate_compiled_nested_subflows(compiled, validated_subflows)

    def validate(self) -> None:
        """
        Validate the graph's structural shape and declared terminal nodes.

        This validation pass is intentionally structural. It does not execute
        node logic or edge conditions. Instead, it checks the graph topology
        using the declared edges, source, and sinks.

        Validation currently enforces:

        - every declared sink is reachable from the source
        - declared sinks do not have outgoing edges
        - every reachable non-sink node has at least one outgoing edge
        - nested subflow graphs validate recursively

        Cycles are allowed as long as the graph still has a reachable sink and
        no reachable non-sink dead ends.

        :raises GraphValidationError: If the graph shape violates Junjo's
            current validation rules.
        """
        self._validate_compiled_graph(self.compile(), validated_subflows=set())

    async def get_next_node(self, store: BaseStore, current_node: Node | _NestableWorkflow) -> Node | _NestableWorkflow:
        """
        Retrieve the next node or subflow in the graph for the given current
        executable.

        This method checks the edges connected to the current executable and
        resolves the next executable based on the conditions defined in those
        edges.

        Junjo uses ordered first-match traversal semantics:

        - outgoing edges are considered in the order they were declared
        - the first edge whose condition resolves to a next executable wins
        - later edges are not evaluated once a match is found

        If no outgoing edge resolves and the current executable is not already
        a declared sink, this method raises ``GraphValidationError``.

        :param store: The store instance to use for resolving the next
            executable.
        :type store: BaseStore
        :param current_node: The current node or subflow in the graph.
        :type current_node: Node | _NestableWorkflow
        :returns: The next node or subflow in the graph.
        :rtype: Node | _NestableWorkflow
        """
        compiled = self.compile()
        for edge in compiled.outgoing_compiled_edges_by_tail_runtime_id.get(current_node.id, ()):
            resolved_edge = await edge.edge_runtime_ref.next_node(store)
            if resolved_edge is not None:
                return resolved_edge

        raise GraphValidationError(
            "Check your Graph. No resolved edges. "
            f"No valid transition found for node or subflow: '{current_node}'."
        )


    def serialize_to_json_string(self) -> str:  # noqa: C901
        """
        Convert the graph to a neutral serialized JSON string.

        The serialized representation treats :class:`~junjo.RunConcurrent`
        instances as subgraphs and includes nested subflow graphs as well.

        The serialized payload includes explicit runtime and structural
        identities for the graph, nodes, and edges. Nested subflow nodes also
        include their child graph structural id plus explicit source and sink
        runtime and structural ids.

        :returns: A JSON string containing the graph structure.
        :rtype: str
        :raises GraphSerializationError: If the graph payload cannot be
            converted into JSON.
        """
        compiled = self.compile()
        nodes_json: list[dict] = []
        edges_json: list[dict] = []
        seen_node_runtime_ids: set[str] = set()

        def collect_serialized_graph(
            graph: CompiledGraph,
            *,
            parent_subflow_runtime_id: str | None = None,
        ) -> None:
            for node in graph.compiled_nodes:
                if node.node_runtime_id not in seen_node_runtime_ids:
                    node_info = {
                        "nodeRuntimeId": node.node_runtime_id,
                        "nodeStructuralId": node.node_structural_id,
                        "nodeType": node.node_type_name,
                        "nodeLabel": node.node_label,
                    }
                    if node.is_concurrent_subgraph:
                        node_info["isConcurrentSubgraph"] = True
                        node_info["childNodeRuntimeIds"] = list(node.child_node_runtime_ids)
                    elif node.is_subflow and node.compiled_subflow_graph is not None:
                        subflow_graph = node.compiled_subflow_graph
                        node_info["isSubflow"] = True
                        node_info["subflowGraphStructuralId"] = subflow_graph.graph_structural_id
                        node_info["subflowSourceNodeRuntimeId"] = subflow_graph.source_node_runtime_id
                        node_info["subflowSourceNodeStructuralId"] = (
                            subflow_graph.compiled_nodes_by_runtime_id[
                                subflow_graph.source_node_runtime_id
                            ].node_structural_id
                        )
                        node_info["subflowSinkNodeRuntimeIds"] = list(subflow_graph.sink_node_runtime_ids)
                        node_info["subflowSinkNodeStructuralIds"] = [
                            subflow_graph.compiled_nodes_by_runtime_id[sink_runtime_id].node_structural_id
                            for sink_runtime_id in subflow_graph.sink_node_runtime_ids
                        ]
                    nodes_json.append(node_info)
                    seen_node_runtime_ids.add(node.node_runtime_id)

                if node.is_subflow and node.compiled_subflow_graph is not None:
                    collect_serialized_graph(
                        node.compiled_subflow_graph,
                        parent_subflow_runtime_id=node.node_runtime_id,
                    )

            for edge in graph.compiled_edges:
                edges_json.append(
                    {
                        "edgeStructuralId": edge.edge_structural_id,
                        "tailNodeRuntimeId": edge.tail_node_runtime_id,
                        "tailNodeStructuralId": edge.tail_node_structural_id,
                        "headNodeRuntimeId": edge.head_node_runtime_id,
                        "headNodeStructuralId": edge.head_node_structural_id,
                        "edgeConditionLabel": edge.edge_condition_label,
                        "edgeScope": (
                            "subflow" if parent_subflow_runtime_id is not None else "explicit"
                        ),
                        "parentSubflowRuntimeId": parent_subflow_runtime_id,
                    }
                )

        collect_serialized_graph(compiled)

        # Final graph dictionary structure
        graph_dict = {
            "v": 1, # Schema version
            "graphStructuralId": compiled.graph_structural_id,
            "nodes": nodes_json,
            "edges": edges_json
        }

        try:
            # Serialize the dictionary to a JSON string
            return json.dumps(graph_dict, indent=2)
        except TypeError as e:
            raise GraphSerializationError(
                f"Failed to serialize graph to JSON: {e}"
            ) from e


    def to_mermaid(self) -> str:
        """
        Converts the graph to Mermaid syntax.

        :raises GraphRenderError: Mermaid output is not implemented yet.
        """
        raise GraphRenderError("Mermaid conversion is not implemented yet.")

    def _build_dot_render_context(
        self,
        graph: dict,
        edge_filter: Callable[[dict], bool],
    ) -> tuple[dict[str, dict], list[dict], set[str], dict[str, dict], dict[str, str], dict[str, str]]:
        nodes_by_id = {node["nodeRuntimeId"]: node for node in graph["nodes"]}
        edges = [edge for edge in graph["edges"] if edge_filter(edge)]

        node_ids: set[str] = set()
        for edge in edges:
            node_ids.update((edge["tailNodeRuntimeId"], edge["headNodeRuntimeId"]))

        for node_id in list(node_ids):
            node = nodes_by_id.get(node_id)
            if node and node.get("isConcurrentSubgraph"):
                node_ids.update(node["childNodeRuntimeIds"])

        clusters = {
            node["nodeRuntimeId"]: node
            for node in graph["nodes"]
            if node.get("isConcurrentSubgraph") and node["nodeRuntimeId"] in node_ids
        }
        entry_anchor = {cluster_id: f"{cluster_id}__entry" for cluster_id in clusters}
        exit_anchor = {cluster_id: f"{cluster_id}__exit" for cluster_id in clusters}
        return nodes_by_id, edges, node_ids, clusters, entry_anchor, exit_anchor

    @staticmethod
    def _dot_anchor(
        node_id: str,
        *,
        is_src: bool,
        clusters: dict[str, dict],
        entry_anchor: dict[str, str],
        exit_anchor: dict[str, str],
    ) -> str:
        if node_id in clusters:
            return exit_anchor[node_id] if is_src else entry_anchor[node_id]
        return node_id

    def _append_dot_header(self, output: list[str], graph_name: str) -> None:
        append = output.append
        append(f'digraph "{graph_name}" {{')
        append("  rankdir=LR;")
        append("  compound=true;")
        append('  node [shape=box, style="rounded,filled", fillcolor="#EFEFEF", fontname="Helvetica", fontsize=10];')
        append('  edge [fontname="Helvetica", fontsize=9];')

    def _append_dot_clusters(
        self,
        output: list[str],
        clusters: dict[str, dict],
        entry_anchor: dict[str, str],
        exit_anchor: dict[str, str],
        nodes_by_id: dict[str, dict],
    ) -> None:
        append = output.append
        for cluster_id, cluster_node in clusters.items():
            append(f'  subgraph "cluster_{cluster_id}" {{')
            append(f'    label="{self._safe_label(cluster_node["nodeLabel"])} (Concurrent)";')
            append('    style="filled"; fillcolor="lightblue"; color="blue";')
            append('    node [fillcolor="lightblue", style="filled,rounded"];')
            append(f'    "{entry_anchor[cluster_id]}" [label="", shape=point, width=0.01, style=invis];')
            append(f'    "{exit_anchor[cluster_id]}"  [label="", shape=point, width=0.01, style=invis];')
            for child_id in cluster_node["childNodeRuntimeIds"]:
                child = nodes_by_id[child_id]
                append(f'    {self._q(child_id)} [label="{self._safe_label(child["nodeLabel"])}"];')
            append("  }")

    def _append_dot_nodes(
        self,
        output: list[str],
        node_ids: set[str],
        clusters: dict[str, dict],
        nodes_by_id: dict[str, dict],
    ) -> None:
        append = output.append
        for node_id in node_ids:
            if node_id in clusters:
                continue
            node = nodes_by_id[node_id]
            if node.get("isSubflow"):
                append(
                    f'  {self._q(node_id)} [label="{self._safe_label(node["nodeLabel"])}", '
                    'shape=component, style="filled,rounded", fillcolor="lightyellow"];'
                )
            else:
                append(f'  {self._q(node_id)} [label="{self._safe_label(node["nodeLabel"])}"];')

    def _dot_edge_attrs(self, edge: dict, clusters: dict[str, dict]) -> list[str]:
        attrs: list[str] = []
        if edge["tailNodeRuntimeId"] in clusters:
            attrs.append(f'ltail="cluster_{edge["tailNodeRuntimeId"]}"')
        if edge["headNodeRuntimeId"] in clusters:
            attrs.append(f'lhead="cluster_{edge["headNodeRuntimeId"]}"')
        if edge.get("edgeConditionLabel"):
            attrs.extend(('style="dashed"', f'label="{self._safe_label(edge["edgeConditionLabel"])}"'))
        else:
            attrs.append('style="solid"')
        return attrs

    def _append_dot_edges(
        self,
        output: list[str],
        edges: list[dict],
        clusters: dict[str, dict],
        entry_anchor: dict[str, str],
        exit_anchor: dict[str, str],
    ) -> None:
        append = output.append
        for edge in edges:
            src = self._dot_anchor(
                edge["tailNodeRuntimeId"],
                is_src=True,
                clusters=clusters,
                entry_anchor=entry_anchor,
                exit_anchor=exit_anchor,
            )
            target = self._dot_anchor(
                edge["headNodeRuntimeId"],
                is_src=False,
                clusters=clusters,
                entry_anchor=entry_anchor,
                exit_anchor=exit_anchor,
            )
            attrs = self._dot_edge_attrs(edge, clusters)
            append(f'  {self._q(src)} -> {self._q(target)} [{", ".join(attrs)}];')

    def _render_dot_graph(
        self,
        graph: dict,
        graph_name: str,
        edge_filter: Callable[[dict], bool],
    ) -> str:
        nodes_by_id, edges, node_ids, clusters, entry_anchor, exit_anchor = self._build_dot_render_context(
            graph, edge_filter
        )
        output: list[str] = []
        self._append_dot_header(output, graph_name)
        self._append_dot_clusters(output, clusters, entry_anchor, exit_anchor, nodes_by_id)
        self._append_dot_nodes(output, node_ids, clusters, nodes_by_id)
        self._append_dot_edges(output, edges, clusters, entry_anchor, exit_anchor)
        output.append("}")
        return "\n".join(output)

    def to_dot_notation(self) -> str:
        """
        Render the Junjo graph as a main overview digraph plus one additional
        digraph for each subflow.
        """
        graph = json.loads(self.serialize_to_json_string())

        dot_parts: list[str] = [
            self._render_dot_graph(
                graph=graph,
                graph_name="G",
                edge_filter=lambda edge: edge["edgeScope"] == "explicit",
            )
        ]

        subflows = [node for node in graph["nodes"] if node.get("isSubflow")]
        for subflow in subflows:
            subflow_id = subflow["nodeRuntimeId"]
            dot_parts.append(
                self._render_dot_graph(
                    graph=graph,
                    graph_name=f"subflow_{subflow_id}",
                    edge_filter=lambda edge, sid=subflow_id: (
                        edge["edgeScope"] == "subflow"
                        and edge["parentSubflowRuntimeId"] == sid
                    ),
                )
            )

        return "\n\n".join(dot_parts)

    @staticmethod
    def _fname(name: str) -> str:
        """Turn any string into a filesystem-friendly stem."""
        return re.sub(r"[^A-Za-z0-9_.-]", "_", name)

    @staticmethod
    def _split_dot_blocks(dot_text: str) -> list[str]:
        return re.split(r"\n(?=digraph )", dot_text.lstrip())

    @staticmethod
    def _extract_digraph_id(dot_block: str) -> str | None:
        match = re.match(r'digraph\s+"?([A-Za-z0-9_]+)"?', dot_block)
        if not match:
            return None
        return match.group(1)

    @staticmethod
    def _clean_graphviz_outputs(out_dir: Path, fmt: str, clean: bool) -> None:
        if not clean:
            return
        for path in out_dir.iterdir():
            if path.suffix in (".dot", f".{fmt}") and path.is_file():
                path.unlink()

    @staticmethod
    def _render_digraph_asset(dot_block: str, out_dir: Path, stem: str, fmt: str, dot_cmd: str) -> Path:
        dot_path = out_dir / f"{stem}.dot"
        img_path = out_dir / f"{stem}.{fmt}"
        dot_path.write_text(dot_block, encoding="utf-8")
        try:
            subprocess.run([dot_cmd, "-T", fmt, str(dot_path), "-o", str(img_path)], check=True)
        except FileNotFoundError as exc:
            raise GraphRenderError(
                f"Failed to render Graphviz asset '{stem}': command '{dot_cmd}' was not found."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise GraphRenderError(
                f"Failed to render Graphviz asset '{stem}': {exc}"
            ) from exc
        return img_path

    def _build_graphviz_label_lookup(self) -> dict[str, str]:
        label_lookup = {"G": "Overview"}
        json_graph = json.loads(self.serialize_to_json_string())
        for node in json_graph["nodes"]:
            if node.get("isSubflow"):
                label_lookup[f"subflow_{node['nodeRuntimeId']}"] = node["nodeLabel"]
        return label_lookup

    @staticmethod
    def _write_graphviz_index(html_path: Path, digraph_files: dict[str, Path], label_lookup: dict[str, str]) -> None:
        html_parts = [
            "<!doctype html><html><head>",
            '<meta charset="utf-8"><title>Junjo Graphs</title>',
            "<style>body{font-family:Helvetica,Arial,sans-serif}"
            "img{max-width:100%;border:1px solid #ccc;margin-bottom:2rem}</style>",
            "</head><body>",
            "<h1>Junjo workflow diagrams</h1>",
        ]
        for name, img in digraph_files.items():
            heading = html.escape(label_lookup.get(name, name))
            html_parts.append(f"<h2>{heading}</h2>")
            html_parts.append(f'<img src="{img.name}" alt="{heading} diagram">')
        html_parts.append("</body></html>")
        html_path.write_text("\n".join(html_parts), encoding="utf-8")

    def export_graphviz_assets(
        self,
        out_dir: str | Path = "graphviz_out",
        fmt: str = "svg",
        dot_cmd: str = "dot",
        open_html: bool = False,
        clean: bool = True,
    ) -> dict[str, Path]:
        """
        Render every digraph produced by :meth:`to_dot_notation` and build a gallery
        HTML page whose headings use the *human* labels (e.g. “SampleSubflow”)
        instead of raw digraph identifiers.

        :returns: An ordered mapping of digraph name to rendered file path, in
            encounter order.
        :rtype: dict[str, Path]
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        self._clean_graphviz_outputs(out_dir, fmt, clean)

        label_lookup = self._build_graphviz_label_lookup()
        blocks = self._split_dot_blocks(self.to_dot_notation())
        top_stem = self._fname(type(self).__name__ or "Overview")

        digraph_files: dict[str, Path] = {}
        for block in blocks:
            dgraph_id = self._extract_digraph_id(block)
            if not dgraph_id:
                continue
            stem = top_stem if dgraph_id == "G" else dgraph_id
            digraph_files[dgraph_id] = self._render_digraph_asset(block, out_dir, stem, fmt, dot_cmd)

        html_path = out_dir / "index.html"
        self._write_graphviz_index(html_path, digraph_files, label_lookup)

        if open_html:
            import webbrowser

            webbrowser.open(html_path.as_uri())

        return digraph_files

    # --------------------------------------------------------------------------- #
    #  Utility helpers                                                            #
    # --------------------------------------------------------------------------- #
    _ID_RX = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


    def _q(self, id_: str) -> str:
        """Quote a Graphviz identifier when needed."""
        return id_ if self._ID_RX.fullmatch(id_) else f'"{id_}"'


    def _safe_label(self, text: str) -> str:
        """Escape quotes so they stay intact in dot files."""
        return html.escape(str(text)).replace('"', r"\"")
