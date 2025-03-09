from junjo.edge import Edge
from junjo.graph import Graph
from junjo.node import Node

from app.workflows_junjo.handle_message.nodes.create_response.node import CreateResponseNode
from app.workflows_junjo.handle_message.nodes.load_contact.node import LoadContactNode
from app.workflows_junjo.handle_message.nodes.load_history.node import LoadHistoryNode
from app.workflows_junjo.handle_message.nodes.save_message.node import SaveMessageNode
from app.workflows_junjo.handle_message.store import MessageWorkflowStore


class SinkNode(Node[MessageWorkflowStore]):
    async def service(self, store: MessageWorkflowStore) -> None:
        print("Running sink node.")
        pass

# Instantiate nodes
save_message_node = SaveMessageNode()
load_history_node = LoadHistoryNode()
load_contact_node = LoadContactNode()
create_response_node = CreateResponseNode()
sink_node = SinkNode()


# Construct a graph
handle_message_graph = Graph(
    source=save_message_node,
    sink=sink_node,
    edges=[
        Edge(tail=save_message_node, head=load_history_node),
        Edge(tail=load_history_node, head=load_contact_node),
        Edge(tail=load_contact_node, head=create_response_node),
        Edge(tail=create_response_node, head=sink_node)
    ]
)
