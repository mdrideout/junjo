from junjo import Edge, Graph, Node, RunConcurrent

from app.workflows.handle_message.conditions.message_directive_is import MessageDirectiveIs
from app.workflows.handle_message.create_response_with_image_subflow.graph import (
    create_response_with_image_subflow_graph,
)
from app.workflows.handle_message.create_response_with_image_subflow.store import (
    CreateResponseWithImageSubflowState,
    CreateResponseWithImageSubflowStore,
)
from app.workflows.handle_message.create_response_with_image_subflow.sub_flow import (
    CreateResponseWithImageSubFlow,
)
from app.workflows.handle_message.nodes.assess_message_directive.node import AssessMessageDirectiveNode
from app.workflows.handle_message.nodes.create_date_idea_response.node import CreateDateIdeaResponseNode
from app.workflows.handle_message.nodes.create_general_response.node import CreateGeneralResponseNode
from app.workflows.handle_message.nodes.create_work_response.node import CreateWorkResponseNode
from app.workflows.handle_message.nodes.load_contact.node import LoadContactNode
from app.workflows.handle_message.nodes.load_history.node import LoadHistoryNode
from app.workflows.handle_message.nodes.save_message.node import SaveMessageNode
from app.workflows.handle_message.schemas import MessageDirective
from app.workflows.handle_message.store import MessageWorkflowStore


class SinkNode(Node[MessageWorkflowStore]):
    async def service(self, store: MessageWorkflowStore) -> None:
        print("Running sink node.")
        pass


def create_handle_message_graph() -> Graph:
    # Instantiate nodes
    save_message_node = SaveMessageNode()
    load_history_node = LoadHistoryNode()
    load_contact_node = LoadContactNode()
    assess_message_directive_node = AssessMessageDirectiveNode()
    create_general_response_node = CreateGeneralResponseNode()
    create_work_response_node = CreateWorkResponseNode()
    create_date_idea_response_node = CreateDateIdeaResponseNode()
    sink_node = SinkNode()

    # Initial Data Load
    initial_data_load = RunConcurrent(
        name="Initial Data Load", items=[save_message_node, load_history_node, load_contact_node]
    )

    # Create Response With Image SubFlow
    create_response_with_image_subflow = CreateResponseWithImageSubFlow(
        graph_factory=create_response_with_image_subflow_graph,
        store_factory=lambda: CreateResponseWithImageSubflowStore(initial_state=CreateResponseWithImageSubflowState()),
    )

    # Construct a graph
    return Graph(
        source=initial_data_load,
        sink=sink_node,
        edges=[
            Edge(tail=initial_data_load, head=assess_message_directive_node),
            # Message Directive Options
            Edge(
                tail=assess_message_directive_node,
                head=create_work_response_node,
                condition=MessageDirectiveIs(directive=MessageDirective.WORK_RELATED_RESPONSE),
            ),
            Edge(
                tail=assess_message_directive_node,
                head=create_date_idea_response_node,
                condition=MessageDirectiveIs(directive=MessageDirective.DATE_IDEA_RESEARCH),
            ),
            Edge(
                tail=assess_message_directive_node,
                head=create_response_with_image_subflow,
                condition=MessageDirectiveIs(directive=MessageDirective.IMAGE_RESPONSE),
            ),
            Edge(tail=assess_message_directive_node, head=create_general_response_node),  # Default
            # Converge
            Edge(tail=create_general_response_node, head=sink_node),
            Edge(tail=create_work_response_node, head=sink_node),
            Edge(tail=create_date_idea_response_node, head=sink_node),
            Edge(tail=create_response_with_image_subflow, head=sink_node),
        ],
    )
