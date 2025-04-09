from junjo.workflow import Subflow

from app.workflows_junjo.handle_message.store import MessageWorkflowState, MessageWorkflowStore
from app.workflows_junjo.test_sub_flow.state import TestSubFlowState
from app.workflows_junjo.test_sub_flow.store import TestSubFlowStore


class TestSubFlow(Subflow[TestSubFlowState, TestSubFlowStore, MessageWorkflowState, MessageWorkflowStore]):
    """A test subflow to run inside the handle_message workflow."""

    async def post_run_actions(self, parent_store):
        """Post run actions that can update the parent store."""
        # Get the parent store
        sub_flow_state = await self.get_state()

        # Update the parent store with values from the SubFlow state
        await parent_store.set_sub_flow_jokes(sub_flow_state.jokes)
