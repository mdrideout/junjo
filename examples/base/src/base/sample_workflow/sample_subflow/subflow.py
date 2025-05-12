

from junjo import Subflow

from base.sample_workflow.sample_subflow.store import SampleSubflowState, SampleSubflowStore
from base.sample_workflow.store import SampleWorkflowState, SampleWorkflowStore


class SampleSubflow(Subflow[SampleSubflowState, SampleSubflowStore, SampleWorkflowState, SampleWorkflowStore]):
    async def pre_run_actions(self, parent_store):
        # Pass the items from the parent store to the subflow store
        parent_state = await parent_store.get_state()
        items = parent_state.items

        # Set the state of the subflow store with the items from the parent store
        await self.store.set_items(items)

    async def post_run_actions(self, parent_store):
        # Update the parent store with values from the Subflow store

        # Get the current state of the subflow store
        subflow_state = await self.get_state()

        # Null check
        if subflow_state.joke is None:
            raise ValueError("Subflow state joke is required for this operation.")

        if subflow_state.fact is None:
            raise ValueError("Subflow state fact is required for this operation.")

        # Update the parent store with the joke and fact from the subflow store
        await parent_store.set_joke(subflow_state.joke)
        await parent_store.set_fact(subflow_state.fact)

