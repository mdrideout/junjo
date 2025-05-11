from __future__ import annotations

import json

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
        Currently Broken: Generates a Mermaid diagram string from the graph.

        The junjo-server telemetry server will produce a proper mermaid diagram for the workflow executions.
        """
        mermaid_str = "graph LR\n"

        # Add nodes
        nodes = {
            node.id: node for node in [self.source, self.sink] +
            [e.tail for e in self.edges] +
            [e.head for e in self.edges]
        }

        for node_id, node in nodes.items():
            node_label = node.__class__.__name__  # Or a custom label from node.name
            mermaid_str += f"    {node_id}[{node_label}]\n"

        # Add edges
        for edge in self.edges:
            tail_id = edge.tail.id
            head_id = edge.head.id
            edge_label = ""
            if edge.condition:
                edge_label = str(edge.condition)
            mermaid_str += f"    {tail_id} --> {edge_label}{head_id}\n"

        return mermaid_str

    def to_dot_notation(self) -> str:
        """Currently Broken: Converts the graph to DOT notation."""

        dot_str = "digraph G {\n"  # Start of DOT graph
        dot_str += "  node [shape=box, style=\"rounded\", fontsize=10];\n" #Added node styling
        dot_str += "  ranksep=0.5; nodesep=1.0;\n" # Adjust spacing between ranks and nodes
        dot_str += "  margin=1.0;\n" # Adjust graph margin


        # Add nodes
        nodes = {node.id: node for node in [self.source, self.sink] +
                 [e.tail for e in self.edges] + [e.head for e in self.edges]}
        for node_id, node in nodes.items():
            node_label = node.__class__.__name__  # Or a custom label from node.name
            dot_str += f'    "{node_id}" [label="{node_label}"];\n'

        # Add edges
        for edge in self.edges:
            tail_id = edge.tail.id
            head_id = edge.head.id
            condition_str = str(edge.condition)
            style = "dashed" if condition_str else "solid"  # Dotted for conditional, solid otherwise
            dot_str += f'    "{tail_id}" -> "{head_id}" [label="{condition_str}", style="{style}"];\n'


        dot_str += "}\n"  # End of DOT graph
        return dot_str

    def to_graphviz(self) -> str:
        """
        Converts the graph to Graphviz format.
        This is a placeholder for future implementation.
        """
        raise NotImplementedError("Graphviz conversion is not implemented yet.")
