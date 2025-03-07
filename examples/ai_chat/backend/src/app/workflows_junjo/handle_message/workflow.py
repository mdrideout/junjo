from junjo.telemetry.hook_manager import HookManager
from junjo.workflow import Workflow

from app.db.models.message.schemas import MessageCreate
from app.workflows_junjo.handle_message.graph import handle_message_graph
from app.workflows_junjo.handle_message.store import MessageWorkflowState, MessageWorkflowStore


async def handle_message_workflow(message: MessageCreate) -> None:
    """Setup and execute the workflow"""

    # Create the store with initial state
    store = MessageWorkflowStore(
        initial_state=MessageWorkflowState(received_message=message)
    )

    # Create the workflow
    workflow = Workflow(
        graph=handle_message_graph,
        initial_store=store,
        hook_manager=HookManager(verbose_logging=True, open_telemetry=True),
    )

    # Execute the workflow
    print("Executing the workflow with initial store state: ", workflow.get_state)
    await workflow.execute()
    final_state = workflow.get_state
    print("Done")

    return
