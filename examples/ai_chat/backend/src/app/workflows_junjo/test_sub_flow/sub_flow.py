from junjo.sub_flow import SubFlow
from loguru import logger

from app.workflows_junjo.handle_message.store import MessageWorkflowStore
from app.workflows_junjo.test_sub_flow.state import TestSubFlowState
from app.workflows_junjo.test_sub_flow.store import TestSubFlowStore


class TestSubFlow(SubFlow[MessageWorkflowStore, TestSubFlowState, TestSubFlowStore]):
    """A test subflow to run inside the handle_message workflow."""

    async def post_run_actions(self, parent_store):
        """Post run actions that can update the parent store."""
        logger.info("Executing post_run_actions for TestSubFlow")

        # Get the parent store
        sub_flow_state = await self.workflow.get_state()

        # Update the parent store with values from the SubFlow state
        await parent_store.set_sub_flow_jokes(self.node, sub_flow_state.jokes)


        return
