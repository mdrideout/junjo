
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

    def get_next_node(self, workflow_id: str, current_node: Node) -> Node:
        matching_edges = [edge for edge in self.edges if edge.tail == current_node]
        resolved_edges = [edge for edge in matching_edges if edge.next_node(workflow_id) is not None]

        if len(resolved_edges) == 0:
            raise ValueError(f"No valid transition found for node '{current_node}'.")
        else:
            resolved_edge = resolved_edges[0].next_node(workflow_id)
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

    def to_dot_notation(self) -> str:
        """Converts the graph to DOT notation."""

        dot_str = "digraph G {\n"  # Start of DOT graph
        dot_str += "  node [shape=box, style=\"rounded\", fontsize=10];\n" #Added node styling
        dot_str += "  ranksep=0.5; nodesep=1.0;\n" # Adjust spacing between ranks and nodes
        dot_str += "  margin=1.0;\n" # Adjust graph margin


        # Add nodes
        nodes = {id(node): node for node in [self.source, self.sink] +
                 [e.tail for e in self.edges] + [e.head for e in self.edges]}
        for node_id, node in nodes.items():
            node_label = node.__class__.__name__  # Or a custom label from node.name
            dot_str += f'    "{node_id}" [label="{node_label}"];\n'

        # Add edges
        for edge in self.edges:
            tail_id = id(edge.tail)
            head_id = id(edge.head)
            condition_str = self._format_condition(edge.condition)
            style = "dashed" if condition_str else "solid"  # Dotted for conditional, solid otherwise
            dot_str += f'    "{tail_id}" -> "{head_id}" [label="{condition_str}", style="{style}"];\n'


        dot_str += "}\n"  # End of DOT graph
        return dot_str

    def _format_condition(self, condition):
        """Helper function to format the condition into a human-readable string."""
        if condition is None:
            return ""
        elif callable(condition): # Handles function conditions
            return condition.__name__ #Use the function's name as a label
        else:
            return str(condition) #Handles other condition types (e.g., strings, booleans)

