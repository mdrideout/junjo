from junjo import Workflow

from app.db.models.message.schemas import MessageCreate
from app.workflows.handle_message.graph import create_handle_message_graph
from app.workflows.handle_message.store import MessageWorkflowState, MessageWorkflowStore


async def run_handle_message_workflow(message: MessageCreate) -> None:
    """Setup and execute the workflow"""

    # Create the workflow
    handle_message_workflow = Workflow[MessageWorkflowState, MessageWorkflowStore](
        name="Handle Message Workflow",
        graph_factory=create_handle_message_graph,
        store_factory=lambda:MessageWorkflowStore(
            initial_state=MessageWorkflowState(received_message=message)
        ),
    )

    # Execute the workflow
    print("Executing handle_message_workflow")
    result = await handle_message_workflow.execute()
    print(f"handle_message_workflow run_id={result.run_id}")
    print("handle_message_workflow is done")

    return
