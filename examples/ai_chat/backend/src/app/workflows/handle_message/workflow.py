from junjo import Workflow
from junjo.telemetry.hook_manager import HookManager

from app.db.models.message.schemas import MessageCreate
from app.workflows.handle_message.graph import handle_message_graph
from app.workflows.handle_message.store import MessageWorkflowState, MessageWorkflowStore


async def run_handle_message_workflow(message: MessageCreate) -> None:
    """Setup and execute the workflow"""

    # Create the workflow
    handle_message_workflow = Workflow[MessageWorkflowState, MessageWorkflowStore](
        name="Handle Message Workflow",
        graph=handle_message_graph,
        store_factory=lambda:MessageWorkflowStore(
            initial_state=MessageWorkflowState(received_message=message)
        ),
        hook_manager=HookManager(verbose_logging=True, open_telemetry=True),
    )

    # Execute the workflow
    print("Executing handle_message_workflow")
    await handle_message_workflow.execute()
    final_state = await handle_message_workflow.get_state()
    print("handle_message_workflow is done")

    return
