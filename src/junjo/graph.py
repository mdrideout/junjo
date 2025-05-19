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


class Graph:
    """
    Represents a directed graph of nodes and edges.
    """
    def __init__(self, source: Node | _NestableWorkflow, sink: Node | _NestableWorkflow, edges: list[Edge]):
        self.source = source
        self.sink = sink
        self.edges = edges

    async def get_next_node(self, store: BaseStore, current_node: Node | _NestableWorkflow) -> Node | _NestableWorkflow:
        """
        Retrieves the next node (or workflow / subflow) in the graph for the given current node.
        This method checks the edges connected to the current node and resolves the next node based on the conditions
        defined in the edges.

        Args:
            store (BaseStore): The store instance to use for resolving the next node.
            current_node (Node | _NestableWorkflow): The current node or subflow in the graph.

        Returns:
            Node | _NestableWorkflow: The next node or subflow in the graph.
        """
        matching_edges = [edge for edge in self.edges if edge.tail == current_node]
        resolved_edges = [edge for edge in matching_edges if await edge.next_node(store) is not None]

        if len(resolved_edges) == 0:
            raise ValueError("Check your Graph. No resolved edges. "
                             f"No valid transition found for node or subflow: '{current_node}'.")
        else:
            resolved_edge = await resolved_edges[0].next_node(store)
            if resolved_edge is None:
                raise ValueError("Check your Graph. Resolved edge is None. "
                                 f"No valid transition found for node or subflow: '{current_node}'")

            return resolved_edge


    def serialize_to_json_string(self) -> str:  # noqa: C901
        """
        Converts the graph to a neutral serialized JSON string,
        representing RunConcurrent instances as subgraphs and includes Subflow graphs as well.

        Returns:
            str: A JSON string containing the graph structure.
        """
        all_nodes_dict: dict[str, Node | _NestableWorkflow] = {} # Dictionary to store unique nodes found
        all_edges_dict: dict[str, Edge] = {} # Dictionary to store all edges including subflow edges
        processed_subflows: set[str] = set() # Track processed subflows to avoid recursion loops

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
                elif (
                    isinstance(node, _NestableWorkflow)
                    and hasattr(node, 'graph')
                    and node.id not in processed_subflows
                ):
                    processed_subflows.add(node.id)  # Mark as processed to avoid cycles

                    # Collect subflow's source, sink and all nodes connected by edges
                    subflow_graph = node.graph
                    collect_nodes(subflow_graph.source)
                    collect_nodes(subflow_graph.sink)

                    # Collect all edges from the subflow
                    for edge in subflow_graph.edges:
                        # Create a unique ID for the subflow edge
                        edge_id = f"subflow_{node.id}_edge_{edge.tail.id}_{edge.head.id}"
                        all_edges_dict[edge_id] = edge
                        collect_nodes(edge.tail)
                        collect_nodes(edge.head)

        # Collect edges from the main graph
        for i, edge in enumerate(self.edges):
            edge_id = f"edge_{edge.tail.id}_{edge.head.id}_{i}"
            all_edges_dict[edge_id] = edge

        # Start node collection
        collect_nodes(self.source)
        collect_nodes(self.sink)
        for edge in self.edges:
            collect_nodes(edge.tail)
            collect_nodes(edge.head)

        # Create nodes list for JSON output
        nodes_json = []
        for node_id, node in all_nodes_dict.items():
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
            elif isinstance(node, _NestableWorkflow) and hasattr(node, 'graph'):
                node_info["isSubflow"] = True
                node_info["subflowSourceId"] = node.graph.source.id
                node_info["subflowSinkId"] = node.graph.sink.id

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
            print(f"Error serializing graph to JSON: {e}")
            error_info = {
                "error": "Failed to serialize graph",
                "detail": str(e),
            }
            return json.dumps(error_info, indent=2)


    def to_mermaid(self) -> str:
        """
        Converts the graph to Mermaid syntax.
        This is a placeholder for future implementation.
        """
        raise NotImplementedError("Mermaid conversion is not implemented yet.")

    def to_dot_notation(self) -> str:  # noqa: C901  (complexity fine for helper)
        """
        Render the Junjo graph as a *main* overview digraph plus one additional
        digraph for **each Subflow**.

        Strategy
        --------
        • In the **overview** we treat every Subflow node as an atomic component
          (shape=component, fillcolour light-yellow).
        • Any `RunConcurrent` node is rendered as a cluster, exactly like before.
        • For every Subflow we emit a *second* `digraph subflow_<id>` that expands
          its internal graph, again treating nested Subflows as atomic macro nodes
          (so the drill-down is recursive).

        """
        graph = json.loads(self.serialize_to_json_string())

        # ----------------------------------------------------------------------- #
        #  Render helpers                                                         #
        # ----------------------------------------------------------------------- #
        def render_graph(
            graph_name: str,
            edge_filter: Callable[[dict], bool],
        ) -> str:
            """
            Build a single digraph string with:
            * RunConcurrent → clusters
            * Subflow       → macro node (no cluster)
            Only edges for which `edge_filter(edge)` is True are included.
            """
            nodes_by_id = {n["id"]: n for n in graph["nodes"]}
            edges = [e for e in graph["edges"] if edge_filter(e)]

            # ---- gather node‑ids that really participate in *this* drawing ---- #
            node_ids: set[str] = set()
            for e in edges:
                node_ids.update((e["source"], e["target"]))

            # if a RunConcurrent appears, also pull in its children
            for nid in list(node_ids):
                n = nodes_by_id.get(nid)
                if n and n.get("isSubgraph"):
                    node_ids.update(n["children"])

            # --------------- meta for RunConcurrent clusters ------------------- #
            clusters = {
                n["id"]: n
                for n in graph["nodes"]
                if n.get("isSubgraph") and n["id"] in node_ids
            }

            entry_anchor = {cid: f"{cid}__entry" for cid in clusters}
            exit_anchor = {cid: f"{cid}__exit" for cid in clusters}

            def _anchor(nid: str, *, is_src: bool) -> str:
                if nid in clusters:
                    return exit_anchor[nid] if is_src else entry_anchor[nid]
                return nid

            # ------------------------------------------------------------------- #
            out: list[str] = []
            a = out.append

            a(f'digraph "{graph_name}" {{')
            a("  rankdir=LR;")
            a("  compound=true;")
            a('  node [shape=box, style="rounded,filled", fillcolor="#EFEFEF", '
            'fontname="Helvetica", fontsize=10];')
            a('  edge [fontname="Helvetica", fontsize=9];')

            # ---------------------- RunConcurrent clusters --------------------- #
            for cid, n in clusters.items():
                a(f'  subgraph "cluster_{cid}" {{')
                a(f'    label="{self._safe_label(n["label"])} (Concurrent)";')
                a('    style="filled"; fillcolor="lightblue"; color="blue";')
                a('    node [fillcolor="lightblue", style="filled,rounded"];')
                # invisible entry/exit points
                a(f'    "{entry_anchor[cid]}" [label="", shape=point, width=0.01, '
                'style=invis];')
                a(f'    "{exit_anchor[cid]}"  [label="", shape=point, width=0.01, '
                'style=invis];')
                for child_id in n["children"]:
                    child = nodes_by_id[child_id]
                    a(f'    {self._q(child_id)} '
                    f'[label="{self._safe_label(child["label"])}"];')
                a("  }")

            # ------------------- ordinary & Subflow macro nodes ---------------- #
            for nid in node_ids:
                if nid in clusters:
                    continue  # already rendered inside its cluster
                n = nodes_by_id[nid]
                if n.get("isSubflow"):
                    # macro representation
                    a(f'  {self._q(nid)} [label="{self._safe_label(n["label"])}", '
                    'shape=component, style="filled,rounded", '
                    'fillcolor="lightyellow"];')
                else:
                    a(f'  {self._q(nid)} [label="{self._safe_label(n["label"])}"];')

            # ------------------------------ edges ------------------------------ #
            for e in edges:
                src = _anchor(e["source"], is_src=True)
                tgt = _anchor(e["target"], is_src=False)

                attrs: list[str] = []
                if e["source"] in clusters:
                    attrs.append(f'ltail="cluster_{e["source"]}"')
                if e["target"] in clusters:
                    attrs.append(f'lhead="cluster_{e["target"]}"')

                if e.get("condition"):
                    attrs.extend(
                        ('style="dashed"', f'label="{self._safe_label(e["condition"])}"')
                    )
                else:
                    attrs.append('style="solid"')

                a(f'  {self._q(src)} -> {self._q(tgt)} [{", ".join(attrs)}];')

            a("}")
            return "\n".join(out)

        # ----------------------------------------------------------------------- #
        #  1) overview graph (explicit edges only)                                #
        # ----------------------------------------------------------------------- #
        dot_parts: list[str] = [
            render_graph(
                graph_name="G",
                edge_filter=lambda e: e["type"] == "explicit"
            )
        ]

        # ----------------------------------------------------------------------- #
        #  2) one digraph per sub‑flow                                            #
        # ----------------------------------------------------------------------- #
        subflows = [
            n for n in graph["nodes"] if n.get("isSubflow")
        ]
        for sf in subflows:
            dot_parts.append(
                render_graph(
                    graph_name=f'subflow_{sf["id"]}',
                    edge_filter=lambda e, sid=sf["id"]: (
                        e["type"] == "subflow" and e["subflowId"] == sid
                    ),
                )
            )

        # join with blank lines so graphviz treats them as separate digraphs
        return "\n\n".join(dot_parts)



    def export_graphviz_assets(
        self,
        out_dir: str | Path = "graphviz_out",
        fmt: str = "svg",
        dot_cmd: str = "dot",
        open_html: bool = False,
        clean: bool = True,
    ) -> dict[str, Path]:
        """
        Render every digraph produced by `to_dot_notation()` and build a gallery
        HTML page whose headings use the *human* labels (e.g. “SampleSubflow”)
        instead of raw digraph identifiers.

        Returns
        -------
        Ordered mapping digraph_name → rendered file path, **in encounter order**.
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # --- delete old artefacts --------------------------------------
        if clean:
            for p in out_dir.iterdir():
                if p.suffix in (".dot", f".{fmt}") and p.is_file():
                    p.unlink()

        # ------------------------------------------------------------------ #
        # 1. Build "digraph name" → human‑readable label lookup              #
        # ------------------------------------------------------------------ #
        label_lookup = {"G": "Overview"}                # first graph
        json_graph = json.loads(self.serialize_to_json_string())
        for node in json_graph["nodes"]:
            if node.get("isSubflow"):
                label_lookup[f"subflow_{node['id']}"] = node["label"]

        # ------------------------------------------------------------------ #
        # 2. Split the combined DOT text into individual blocks              #
        #    (order preserved)                                               #
        # ------------------------------------------------------------------ #
        dot_text = self.to_dot_notation().lstrip()
        blocks: list[str] = re.split(r"\n(?=digraph )", dot_text)

        # ------------------------------------------------------------------ #
        # choose a safe filename stem                                        #
        # ------------------------------------------------------------------ #
        def _fname(s: str) -> str:
            """Turn any string into a filesystem‑friendly stem."""
            return re.sub(r"[^A-Za-z0-9_.-]", "_", s)

        top_stem = _fname(type(self).__name__ or "Overview")   # e.g.  MyWorkflow

        digraph_files: dict[str, Path] = {}                    # preserves order
        for block in blocks:
            m = re.match(r'digraph\s+"?([A-Za-z0-9_]+)"?', block)
            if not m:
                continue
            dgraph_id = m.group(1)          # raw identifier: "G", "subflow_<id>", …

            # --------------------------------------------- #
            # decide the output filename stem               #
            # --------------------------------------------- #
            if dgraph_id == "G":            # the primary overview graph
                stem = top_stem
            else:                           # keep sub‑flow identifier for others
                stem = dgraph_id

            dot_path = out_dir / f"{stem}.dot"
            img_path = out_dir / f"{stem}.{fmt}"

            dot_path.write_text(block, encoding="utf-8")

            subprocess.run(
                [dot_cmd, "-T", fmt, str(dot_path), "-o", str(img_path)],
                check=True,
            )

            # keep mapping by digraph‑identifier, not by filename
            digraph_files[dgraph_id] = img_path

        # ------------------------------------------------------------------ #
        # 3. Build index.html (respect encounter order)                      #
        # ------------------------------------------------------------------ #
        html_path = out_dir / "index.html"
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
