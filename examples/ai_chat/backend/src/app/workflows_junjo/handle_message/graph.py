from junjo.edge import Edge
from junjo.graph import Graph
from junjo.node import Node

from app.workflows_junjo.handle_message.nodes.save_message.node import SaveMessageNode
from app.workflows_junjo.handle_message.store import MessageWorkflowStore


class SinkNode(Node[MessageWorkflowStore]):
    async def service(self, store: MessageWorkflowStore) -> None:
        print("Running sink node.")
        pass

# Instantiate nodes
save_message_node = SaveMessageNode()
sink_node = SinkNode()


# Construct a graph
handle_message_graph = Graph(
    source=save_message_node,
    sink=save_message_node,
    edges=[
        Edge(tail=save_message_node, head=save_message_node),
    ]
)
