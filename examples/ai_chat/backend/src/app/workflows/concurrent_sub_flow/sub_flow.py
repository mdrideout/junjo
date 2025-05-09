from junjo.workflow import Subflow

from app.workflows.concurrent_sub_flow.state import ConcurrentSubFlowState
from app.workflows.concurrent_sub_flow.store import ConcurrentSubFlowStore
from app.workflows.handle_message.store import MessageWorkflowState, MessageWorkflowStore


class ConcurrentSubFlow(Subflow[ConcurrentSubFlowState, ConcurrentSubFlowStore, MessageWorkflowState, MessageWorkflowStore]):
    """A Sub subflow to run inside the handle_message workflow."""

    async def pre_run_actions(self, parent_store):
        pass

    async def post_run_actions(self, parent_store):
        """Post run actions that can update the parent store."""
        # Get this workflow's state
        sub_flow_state = await self.get_state()

        parent_state = await parent_store.get_state()

        # Update the parent store with values from the SubFlow state
        print(f"Updating parent store with subflow state: {sub_flow_state.poems}")
        await parent_store.set_sub_flow_poems(sub_flow_state.poems)
        parent_state = await parent_store.get_state()
        print(f"Parent store facts state after: {parent_state.sub_flow_poems}")
