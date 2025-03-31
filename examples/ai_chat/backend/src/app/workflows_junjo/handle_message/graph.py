from junjo.edge import Edge
from junjo.graph import Graph
from junjo.node import Node

from app.workflows_junjo.handle_message.nodes.assess_message_directive.node import AssessMessageDirectiveNode
from app.workflows_junjo.handle_message.nodes.create_general_response.node import CreateGeneralResponseNode
from app.workflows_junjo.handle_message.nodes.load_contact.node import LoadContactNode
from app.workflows_junjo.handle_message.nodes.load_history.node import LoadHistoryNode
from app.workflows_junjo.handle_message.nodes.save_message.node import SaveMessageNode
from app.workflows_junjo.handle_message.store import MessageWorkflowStore
from app.workflows_junjo.handle_message.nodes.create_work_response.node import CreateWorkResponseNode
from app.workflows_junjo.handle_message.conditions.message_directive_is import MessageDirectiveIs
from app.workflows_junjo.handle_message.schemas import MessageDirective
from app.workflows_junjo.handle_message.nodes.create_date_idea_response.node import CreateDateIdeaResponseNode


class SinkNode(Node[MessageWorkflowStore]):
    async def service(self, store: MessageWorkflowStore) -> None:
        print("Running sink node.")
        pass

# Instantiate nodes
save_message_node = SaveMessageNode()
load_history_node = LoadHistoryNode()
load_contact_node = LoadContactNode()
assess_message_directive_node = AssessMessageDirectiveNode()
create_general_response_node = CreateGeneralResponseNode()
create_work_response_node = CreateWorkResponseNode()
create_date_idea_response_node = CreateDateIdeaResponseNode()
sink_node = SinkNode()

# Construct a graph
handle_message_graph = Graph(
    source=save_message_node,
    sink=sink_node,
    edges=[
        Edge(tail=save_message_node, head=load_history_node),
        Edge(tail=load_history_node, head=load_contact_node),
        Edge(tail=load_contact_node, head=assess_message_directive_node),

        # Message Directive Options
        Edge(tail=assess_message_directive_node, head=create_work_response_node, condition=MessageDirectiveIs(directive=MessageDirective.WORK_RELATED_RESPONSE)),
        Edge(tail=assess_message_directive_node, head=create_date_idea_response_node, condition=MessageDirectiveIs(directive=MessageDirective.DATE_IDEA_RESEARCH)),
        Edge(tail=assess_message_directive_node, head=create_general_response_node), # Default

        Edge(tail=create_general_response_node, head=sink_node),
        Edge(tail=create_work_response_node, head=sink_node),
        Edge(tail=create_date_idea_response_node, head=sink_node)
    ]
)
