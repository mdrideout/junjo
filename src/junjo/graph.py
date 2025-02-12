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
