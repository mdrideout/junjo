from junjo.workflow import Subflow

from app.workflows.sub_sub_flow.state import SubSubFlowState
from app.workflows.sub_sub_flow.store import SubSubFlowStore
from app.workflows.test_sub_flow.state import TestSubFlowState
from app.workflows.test_sub_flow.store import TestSubFlowStore


class SubSubFlow(Subflow[SubSubFlowState, SubSubFlowStore, TestSubFlowState, TestSubFlowStore]):
    """A Sub subflow to run inside the handle_message workflow."""

    async def pre_run_actions(self, parent_store):
        pass

    async def post_run_actions(self, parent_store):
        """Post run actions that can update the parent store."""
        # Get this workflow's state
        sub_flow_state = await self.get_state()

        parent_state = await parent_store.get_state()

        # Update the parent store with values from the SubFlow state
        print(f"Updating parent store with subflow state: {sub_flow_state.facts}")
        await parent_store.set_subflow_facts(sub_flow_state.facts)
        parent_state = await parent_store.get_state()
        print(f"Parent store facts state after: {parent_state.subflow_facts}")
