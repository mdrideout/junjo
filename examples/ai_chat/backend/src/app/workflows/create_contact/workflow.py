from junjo.telemetry.hook_manager import HookManager
from junjo.workflow import Workflow

from app.db.queries.create_setup_contact.schemas import CreateSetupContactResponse
from app.workflows.create_contact.graph import create_create_contact_graph
from app.workflows.create_contact.store import CreateContactState, CreateContactStore


async def run_create_contact_workflow() -> CreateSetupContactResponse:
    """
    Create Contact Workflow

    This workflow is responsible for creating a contact and saving it to the database.

    returns:
        CreateSetupContactResponse: The resulting contact and new chat with this person.
    """

    # Create the workflow
    create_contact_workflow = Workflow[CreateContactState, CreateContactStore](
        name="Create Contact Workflow",
        graph_factory=create_create_contact_graph,
        store_factory=lambda: CreateContactStore(
            initial_state=CreateContactState()
        ),
        hook_manager=HookManager(verbose_logging=True, open_telemetry=True),
    )

    # Execute the workflow
    print("Executing create_contact_workflow")
    await create_contact_workflow.execute()
    final_state = await create_contact_workflow.get_state()
    print("create_contact_workflow is done")

    if final_state.final_contact is None:
        raise ValueError("Final contact is None. Workflow execution failed.")

    return final_state.final_contact
