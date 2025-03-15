
import json

from junjo.node import Node
from junjo.react_flow.schemas import (
    ReactFlowEdge,
    ReactFlowJsonObject,
    ReactFlowNode,
    ReactFlowNodeData,
    ReactFlowPosition,
    ReactFlowViewport,
)
from junjo.store import BaseStore

from .edge import Edge  # Assuming Transition is in a 'transition.py' file


class Graph:
    """
    Represents a directed graph of nodes and edges.
    """
    def __init__(self, source: Node, sink: Node, edges: list[Edge]):
        self.source = source
        self.sink = sink
        self.edges = edges

    # TODO: This needs work because it currently requires a workflow id to complete
    # def validate_graph(self):
    #     """Validate that it is possible to get to the sink from the source."""
    #     current_node = self.source
    #     while current_node != self.sink:
    #         try:
    #             current_node = self.get_next_node(current_node)
    #         except ValueError:
    #             return False
    #     return True


    async def get_next_node(self, store: BaseStore, current_node: Node) -> Node:
        matching_edges = [edge for edge in self.edges if edge.tail == current_node]
        resolved_edges = [edge for edge in matching_edges if await edge.next_node(store) is not None]

        if len(resolved_edges) == 0:
            raise ValueError(f"No valid transition found for node '{current_node}'.")
        else:
            resolved_edge = await resolved_edges[0].next_node(store)
            if resolved_edge is None:
                raise ValueError("No valid transition found for node '{current_node}'")

            return resolved_edge

    def to_mermaid(self) -> str:
        """Generates a Mermaid diagram string from the graph."""
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
        nodes = {node.id: node for node in [self.source, self.sink] +
                 [e.tail for e in self.edges] + [e.head for e in self.edges]}
        for node_id, node in nodes.items():
            node_label = node.__class__.__name__  # Or a custom label from node.name
            dot_str += f'    "{node_id}" [label="{node_label}"];\n'

        # Add edges
        for edge in self.edges:
            tail_id = edge.tail.id
            head_id = edge.head.id
            condition_str = self._format_condition(edge.condition)
            style = "dashed" if condition_str else "solid"  # Dotted for conditional, solid otherwise
            dot_str += f'    "{tail_id}" -> "{head_id}" [label="{condition_str}", style="{style}"];\n'


        dot_str += "}\n"  # End of DOT graph
        return dot_str

    def to_react_flow(self) -> ReactFlowJsonObject:
        """Converts the graph to a ReactFlowJsonObject."""
        nodes: list[ReactFlowNode] = []
        edges: list[ReactFlowEdge] = []

        # Add nodes
        all_nodes = {node.id: node for node in [self.source, self.sink] +
                     [e.tail for e in self.edges] + [e.head for e in self.edges]}
        for node_id, node in all_nodes.items():
            nodes.append(ReactFlowNode(
                id=node_id,
                data=ReactFlowNodeData(label=node.__class__.__name__),
                position=ReactFlowPosition(x=0, y=0)  # The frontend can calculate these dynamically
            ))

        # Add edges
        for edge in self.edges:
            tail_id = edge.tail.id
            head_id = edge.head.id
            edges.append(ReactFlowEdge(
                id=f"{tail_id}-{head_id}",
                source=tail_id,
                target=head_id,
                label=edge.condition.__name__ if edge.condition else None
            ))

        viewport = ReactFlowViewport(x=0, y=0, zoom=1)
        return ReactFlowJsonObject(nodes=nodes, edges=edges, viewport=viewport)

    def serialize_to_json_string(self) -> str:
        """
        Converts the graph to a neutral unopinionated serialized JSON string.

        Returns:
            dict: A JSON-serializable dictionary containing the graph structure
        """
        # Collect all nodes
        all_nodes = {node.id: node for node in [self.source, self.sink] +
                    [e.tail for e in self.edges] + [e.head for e in self.edges]}

        # Create nodes list
        nodes = [
            {
                "id": node_id,
                "type": node.__class__.__name__,
                "label": node.__class__.__name__
            }
            for node_id, node in all_nodes.items()
        ]

        # Create edges list
        edges = [
            {
                "id": f"{edge.tail.id}_{edge.head.id}",
                "source": str(edge.tail.id),
                "target": str(edge.head.id),
                "condition": edge.condition.__name__ if edge.condition else None
            }
            for edge in self.edges
        ]

        graph_dict = {
            "v": 1,
            "nodes": nodes,
            "edges": edges
        }

        return json.dumps(graph_dict)



    def _format_condition(self, condition):
        """Helper function to format the condition into a human-readable string."""
        if condition is None:
            return ""
        elif callable(condition): # Handles function conditions
            return condition.__name__ #Use the function's name as a label
        else:
            return str(condition) #Handles other condition types (e.g., strings, booleans)

