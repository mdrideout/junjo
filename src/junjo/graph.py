from typing import Any

from junjo.node import Node

from .edge import Edge  # Assuming Transition is in a 'transition.py' file


class Graph:
    """
    Represents a directed graph of nodes and edges.
    """
    def __init__(self, source: Node, sink: Node, edges: list[Edge]):
        self.source = source
        self.sink = sink
        self.edges = edges

    def get_next_node(self, current_node: Node, context: dict[str, Any]) -> Node:
        matching_edges = [edge for edge in self.edges if edge.tail == current_node]
        resolved_edges = [edge for edge in matching_edges if edge.next_node(context) is not None]

        if len(resolved_edges) == 0:
            raise ValueError(f"No valid transition found for node '{current_node}'.")
        else:
            resolved_edge = resolved_edges[0].next_node(context)
            if resolved_edge is None:
                raise ValueError("No valid transition found for node '{current_node}'")

            return resolved_edge

    def to_mermaid(self) -> str:
        """Generates a Mermaid diagram string from the graph."""
        mermaid_str = "graph LR\n"

        # Add nodes
        nodes = {
            id(node): node for node in [self.source, self.sink] +
            [e.tail for e in self.edges] +
            [e.head for e in self.edges]
        }

        for node_id, node in nodes.items():
            node_label = node.__class__.__name__  # Or a custom label from node.name
            mermaid_str += f"    {node_id}[{node_label}]\n"

        # Add edges
        for edge in self.edges:
            tail_id = id(edge.tail)
            head_id = id(edge.head)
            edge_label = ""
            if edge.condition:
                edge_label = "|Condition|"  # Or a more descriptive label
            mermaid_str += f"    {tail_id} --> {edge_label}{head_id}\n"

        return mermaid_str
