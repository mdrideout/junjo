
import json

from junjo.node import Node
from junjo.node_gather import NodeGather
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
                edge_label = str(edge.condition)
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
            condition_str = str(edge.condition)
            style = "dashed" if condition_str else "solid"  # Dotted for conditional, solid otherwise
            dot_str += f'    "{tail_id}" -> "{head_id}" [label="{condition_str}", style="{style}"];\n'


        dot_str += "}\n"  # End of DOT graph
        return dot_str


    def serialize_to_json_string(self) -> str:  # noqa: C901
        """
        Converts the graph to a neutral serialized JSON string,
        representing NodeGather instances as subgraphs.

        Returns:
            str: A JSON string containing the graph structure.
        """
        all_nodes_dict: dict[str, Node] = {} # Dictionary to store unique nodes found

        # Recursive helper function to find all nodes, including those inside NodeGather
        def collect_nodes(node: Node | None):
            # Basic validation: Ensure node is a Node instance and has an ID
            if not isinstance(node, Node) or not hasattr(node, 'id'):
                 print(f"Warning: Item '{node}' is not a valid Node with an id, skipping collection.")
                 return

            if node.id not in all_nodes_dict:
                all_nodes_dict[node.id] = node
                # If it's a NodeGather, recursively collect the nodes it contains
                if isinstance(node, NodeGather) and hasattr(node, 'nodes'):
                    for internal_node in node.nodes:
                        # Recursively call collect_nodes for internal nodes
                        collect_nodes(internal_node) # The helper handles None/invalid types

        # --- Start Node Collection ---
        collect_nodes(self.source)
        collect_nodes(self.sink)
        for edge in self.edges:
            collect_nodes(edge.tail)
            collect_nodes(edge.head)
        # --- End Node Collection ---

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

            # ** Add subgraph representation for NodeGather **
            if isinstance(node, NodeGather):
                node_info["isSubgraph"] = True
                # Ensure children are valid Nodes with IDs before adding
                children_ids = [
                    n.id for n in node.nodes
                    if isinstance(n, Node) and hasattr(n, 'id')
                ]
                node_info["children"] = children_ids

            nodes_json.append(node_info)

        # Create explicit edges list for JSON output
        edges_json = []
        for i, edge in enumerate(self.edges):
             # Generate a unique ID for the edge
             # Using index 'i' guarantees uniqueness within this serialization context
             edge_id = f"edge_{str(edge.tail.id)}_{str(edge.head.id)}_{i}"

             edges_json.append({
                 "id": edge_id,
                 "source": str(edge.tail.id),
                 "target": str(edge.head.id),
                 "condition": str(edge.condition) if edge.condition else None,
                 "type": "explicit" # Indicate this is from the main graph definition
             })

        # Final graph dictionary structure
        graph_dict = {
            "v": 1, # Schema version
            "nodes": nodes_json,
            "edges": edges_json
        }

        try:
            # Serialize the dictionary to a JSON string
            # Use indent=2 for readability during development, can remove for production
            return json.dumps(graph_dict, indent=2)
        except TypeError as e:
            print(f"Error serializing graph to JSON: {e}")
            # Return a JSON formatted error message
            error_info = {
                "error": "Failed to serialize graph",
                "detail": str(e),
            }
            # Optionally include partial data for debugging if safe:
            # error_info["partial_nodes"] = nodes_json
            # error_info["partial_edges"] = edges_json
            return json.dumps(error_info, indent=2)
