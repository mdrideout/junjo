from __future__ import annotations

import html
import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

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

    Junjo does not yet expose a full graph compilation phase, but this type is
    reserved for that future hardening step so callers can distinguish compile
    failures from validation, serialization, and rendering failures.
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

    def _collect_structural_nodes(self) -> dict[str, Node | _NestableWorkflow]:
        all_nodes: dict[str, Node | _NestableWorkflow] = {self.source.id: self.source}
        for sink in self.sinks:
            all_nodes[sink.id] = sink
        for edge in self.edges:
            all_nodes[edge.tail.id] = edge.tail
            all_nodes[edge.head.id] = edge.head
        return all_nodes

    def _build_outgoing_edges(self) -> dict[str, list[Edge]]:
        outgoing_edges: dict[str, list[Edge]] = {}
        for edge in self.edges:
            outgoing_edges.setdefault(edge.tail.id, []).append(edge)
        return outgoing_edges

    def _validate_sinks_have_no_outgoing_edges(
        self,
        outgoing_edges: dict[str, list[Edge]],
    ) -> None:
        for sink in self.sinks:
            if outgoing_edges.get(sink.id):
                raise GraphValidationError(
                    f"Declared sink '{sink}' has outgoing edges."
                )

    def _collect_reachable_nodes(
        self,
        outgoing_edges: dict[str, list[Edge]],
    ) -> dict[str, Node | _NestableWorkflow]:
        reachable_nodes: dict[str, Node | _NestableWorkflow] = {}
        queue: list[Node | _NestableWorkflow] = [self.source]
        while queue:
            current = queue.pop(0)
            if current.id in reachable_nodes:
                continue
            reachable_nodes[current.id] = current
            for edge in outgoing_edges.get(current.id, []):
                if edge.head.id not in reachable_nodes:
                    queue.append(edge.head)
        return reachable_nodes

    def _validate_reachable_non_sink_nodes(
        self,
        reachable_nodes: dict[str, Node | _NestableWorkflow],
        outgoing_edges: dict[str, list[Edge]],
    ) -> None:
        sink_ids = {sink.id for sink in self.sinks}
        for node_id, node in reachable_nodes.items():
            if node_id in sink_ids:
                continue
            if not outgoing_edges.get(node_id):
                raise GraphValidationError(
                    f"Reachable non-sink '{node}' dead-ends without an outgoing edge."
                )

    def _validate_declared_sinks_are_reachable(
        self,
        reachable_nodes: dict[str, Node | _NestableWorkflow],
    ) -> None:
        for sink in self.sinks:
            if sink.id not in reachable_nodes:
                raise GraphValidationError(
                    f"Declared sink '{sink}' is unreachable from the source."
                )

    def _validate_nested_subflows(
        self,
        all_nodes: dict[str, Node | _NestableWorkflow],
        validated_subflows: set[str],
    ) -> None:
        for node in all_nodes.values():
            if isinstance(node, _NestableWorkflow) and node.id not in validated_subflows:
                validated_subflows.add(node.id)
                node._graph_factory().validate(validated_subflows)

    def validate(self, _validated_subflows: set[str] | None = None) -> None:
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
        validated_subflows = set() if _validated_subflows is None else _validated_subflows
        all_nodes = self._collect_structural_nodes()
        outgoing_edges = self._build_outgoing_edges()

        self._validate_sinks_have_no_outgoing_edges(outgoing_edges)

        reachable_nodes = self._collect_reachable_nodes(outgoing_edges)
        self._validate_reachable_non_sink_nodes(reachable_nodes, outgoing_edges)
        self._validate_declared_sinks_are_reachable(reachable_nodes)
        self._validate_nested_subflows(all_nodes, validated_subflows)

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
        matching_edges = [edge for edge in self.edges if edge.tail == current_node]
        for edge in matching_edges:
            resolved_edge = await edge.next_node(store)
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

        Nested subflow payloads include:

        - ``subflowSourceId`` for the child graph's source
        - ``subflowSinkIds`` for the child graph's explicit terminal nodes

        :returns: A JSON string containing the graph structure.
        :rtype: str
        :raises GraphSerializationError: If the graph payload cannot be
            converted into JSON.
        """
        all_nodes_dict: dict[str, Node | _NestableWorkflow] = {} # Dictionary to store unique nodes found
        all_edges_dict: dict[str, Edge] = {} # Dictionary to store all edges including subflow edges
        processed_subflows: set[str] = set() # Track processed subflows to avoid recursion loops
        subflow_graphs: dict[str, Graph] = {} # Cache one graph snapshot per subflow for this pass

        def get_subflow_graph(subflow: _NestableWorkflow) -> Graph:
            if subflow.id not in subflow_graphs:
                subflow_graphs[subflow.id] = subflow._graph_factory()
            return subflow_graphs[subflow.id]

        # Recursive helper function to find all nodes, including those inside RunConcurrent and Subflows
        def collect_nodes(node: Node | _NestableWorkflow | None):
            if node is None:
                return

            # Skip if not a Node or _NestableWorkflow or doesn't have an ID
            if not (isinstance(node, Node) or isinstance(node, _NestableWorkflow)) or not hasattr(node, 'id'):
                print(f"Warning: Item '{node}' is not a valid Node or Workflow with an id, skipping collection.")
                return

            if node.id not in all_nodes_dict:
                all_nodes_dict[node.id] = node

                # If it's a RunConcurrent, recursively collect the items it contains
                if isinstance(node, RunConcurrent) and hasattr(node, 'items'):
                    for run_concurrent_item in node.items:
                        collect_nodes(run_concurrent_item)

                # If it's a Subflow (inherits from _NestableWorkflow), recursively collect its graph
                elif isinstance(node, _NestableWorkflow) and node.id not in processed_subflows:
                    processed_subflows.add(node.id)  # Mark as processed to avoid cycles

                    # Collect subflow's source, sinks, and all nodes connected by edges.
                    # Reuse a single graph snapshot for the entire serialization pass.
                    subflow_graph = get_subflow_graph(node)
                    collect_nodes(subflow_graph.source)
                    for sink in subflow_graph.sinks:
                        collect_nodes(sink)

                    # Collect all edges from the subflow
                    for i, edge in enumerate(subflow_graph.edges):
                        # Create a unique ID for the subflow edge
                        edge_id = f"subflow_{node.id}_edge_{edge.tail.id}_{edge.head.id}_{i}"
                        all_edges_dict[edge_id] = edge
                        collect_nodes(edge.tail)
                        collect_nodes(edge.head)

        # Collect edges from the main graph
        for i, edge in enumerate(self.edges):
            edge_id = f"edge_{edge.tail.id}_{edge.head.id}_{i}"
            all_edges_dict[edge_id] = edge

        # Start node collection
        collect_nodes(self.source)
        for sink in self.sinks:
            collect_nodes(sink)
        for edge in self.edges:
            collect_nodes(edge.tail)
            collect_nodes(edge.head)

        # Create nodes list for JSON output
        nodes_json = []
        for _node_id, node in all_nodes_dict.items():
            # Determine Label: Prioritize 'label', then 'name', then class name
            label = getattr(node, 'label', None) or \
                    getattr(node, 'name', None) or \
                    node.__class__.__name__

            node_info = {
                "id": node.id,
                "type": node.__class__.__name__,
                "label": label
            }

            # Add subgraph representation for RunConcurrent
            if isinstance(node, RunConcurrent):
                node_info["isSubgraph"] = True
                children_ids = [
                    n.id for n in node.items
                    if (isinstance(n, Node) or isinstance(n, _NestableWorkflow)) and hasattr(n, 'id')
                ]
                node_info["children"] = children_ids

            # Add subflow representation for Subflows
            elif isinstance(node, _NestableWorkflow):
                node_info["isSubflow"] = True
                subflow_graph = get_subflow_graph(node)
                node_info["subflowSourceId"] = subflow_graph.source.id
                node_info["subflowSinkIds"] = [sink.id for sink in subflow_graph.sinks]

            nodes_json.append(node_info)

        # Create explicit edges list for JSON output
        edges_json = []
        for edge_id, edge in all_edges_dict.items():
            # Determine if this is a subflow edge
            is_subflow_edge = edge_id.startswith("subflow_")
            subflow_id = None
            if is_subflow_edge:
                # Extract the subflow ID from the edge_id (between "subflow_" and "_edge_")
                subflow_id = edge_id.split("_edge_")[0].replace("subflow_", "")

            edges_json.append({
                "id": edge_id,
                "source": str(edge.tail.id),
                "target": str(edge.head.id),
                "condition": str(edge.condition) if edge.condition else None,
                "type": "subflow" if is_subflow_edge else "explicit",
                "subflowId": subflow_id if is_subflow_edge else None
            })

        # Final graph dictionary structure
        graph_dict = {
            "v": 1, # Schema version
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
        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        edges = [edge for edge in graph["edges"] if edge_filter(edge)]

        node_ids: set[str] = set()
        for edge in edges:
            node_ids.update((edge["source"], edge["target"]))

        for node_id in list(node_ids):
            node = nodes_by_id.get(node_id)
            if node and node.get("isSubgraph"):
                node_ids.update(node["children"])

        clusters = {
            node["id"]: node
            for node in graph["nodes"]
            if node.get("isSubgraph") and node["id"] in node_ids
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
            append(f'    label="{self._safe_label(cluster_node["label"])} (Concurrent)";')
            append('    style="filled"; fillcolor="lightblue"; color="blue";')
            append('    node [fillcolor="lightblue", style="filled,rounded"];')
            append(f'    "{entry_anchor[cluster_id]}" [label="", shape=point, width=0.01, style=invis];')
            append(f'    "{exit_anchor[cluster_id]}"  [label="", shape=point, width=0.01, style=invis];')
            for child_id in cluster_node["children"]:
                child = nodes_by_id[child_id]
                append(f'    {self._q(child_id)} [label="{self._safe_label(child["label"])}"];')
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
                    f'  {self._q(node_id)} [label="{self._safe_label(node["label"])}", '
                    'shape=component, style="filled,rounded", fillcolor="lightyellow"];'
                )
            else:
                append(f'  {self._q(node_id)} [label="{self._safe_label(node["label"])}"];')

    def _dot_edge_attrs(self, edge: dict, clusters: dict[str, dict]) -> list[str]:
        attrs: list[str] = []
        if edge["source"] in clusters:
            attrs.append(f'ltail="cluster_{edge["source"]}"')
        if edge["target"] in clusters:
            attrs.append(f'lhead="cluster_{edge["target"]}"')
        if edge.get("condition"):
            attrs.extend(('style="dashed"', f'label="{self._safe_label(edge["condition"])}"'))
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
                edge["source"],
                is_src=True,
                clusters=clusters,
                entry_anchor=entry_anchor,
                exit_anchor=exit_anchor,
            )
            target = self._dot_anchor(
                edge["target"],
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
                edge_filter=lambda edge: edge["type"] == "explicit",
            )
        ]

        subflows = [node for node in graph["nodes"] if node.get("isSubflow")]
        for subflow in subflows:
            subflow_id = subflow["id"]
            dot_parts.append(
                self._render_dot_graph(
                    graph=graph,
                    graph_name=f"subflow_{subflow_id}",
                    edge_filter=lambda edge, sid=subflow_id: edge["type"] == "subflow" and edge["subflowId"] == sid,
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
                label_lookup[f"subflow_{node['id']}"] = node["label"]
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
