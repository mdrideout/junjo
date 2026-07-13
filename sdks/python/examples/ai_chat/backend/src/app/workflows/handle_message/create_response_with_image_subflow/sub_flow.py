from junjo.workflow import Subflow

from app.workflows.handle_message.create_response_with_image_subflow.store import (
    CreateResponseWithImageSubflowState,
    CreateResponseWithImageSubflowStore,
)
from app.workflows.handle_message.store import MessageWorkflowState, MessageWorkflowStore


class CreateResponseWithImageSubFlow(
    Subflow[
        CreateResponseWithImageSubflowState,
        CreateResponseWithImageSubflowStore,
        MessageWorkflowState,
        MessageWorkflowStore,
    ]
):
    """A subflow for generating an image for a chat response."""

    async def pre_run_actions(self, parent_store, subflow_store):
        """Pre run actions that interface with the parent store."""

        # Pass the parent state to this subflow so we can access the values
        parent_state = await parent_store.get_state()
        await subflow_store.set_parent_state(parent_state)

    async def post_run_actions(self, parent_store, subflow_store):
        """Post run actions that can update the parent store."""
        pass
