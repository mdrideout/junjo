from junjo.workflow import Subflow

from app.workflows.handle_message.store import MessageWorkflowState, MessageWorkflowStore
from app.workflows.test_sub_flow.state import TestSubFlowState
from app.workflows.test_sub_flow.store import TestSubFlowStore


class TestSubFlow(Subflow[TestSubFlowState, TestSubFlowStore, MessageWorkflowState, MessageWorkflowStore]):
    """A test subflow to run inside the handle_message workflow."""

    async def pre_run_actions(self, parent_store):
        pass

    async def post_run_actions(self, parent_store):
        """Post run actions that can update the parent store."""
        # Get this workflow's state
        sub_flow_state = await self.get_state()

        parent_state = await parent_store.get_state()

        # Update the parent store with values from the SubFlow state
        print(f"Updating parent store with subflow state: {sub_flow_state}")
        await parent_store.set_sub_flow_jokes(sub_flow_state.jokes)
        await parent_store.set_sub_sub_flow_facts(sub_flow_state.subflow_facts)
        parent_state = await parent_store.get_state()
        print(f"Parent store state after: {parent_state}")
