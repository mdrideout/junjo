from junjo.workflow import Subflow

from app.workflows.create_contact.avatar_subflow.store import AvatarSubflowState, AvatarSubflowStore
from app.workflows.create_contact.store import CreateContactState, CreateContactStore


class AvatarSubFlow(Subflow[AvatarSubflowState, AvatarSubflowStore, CreateContactState, CreateContactStore]):
    """A subflow for generating an avatar."""

    async def pre_run_actions(self, parent_store):
        """Pre run actions that interface with the parent store."""

        # Pass the parent state to this subflow so we can access the values
        parent_state = await parent_store.get_state()
        await self.store.set_parent_state(parent_state)

    async def post_run_actions(self, parent_store):
        """Post run actions that can update the parent store."""
        # Get this workflow's state
        avatar_subflow_state = await self.get_state()

        if avatar_subflow_state.avatar_id is None:
            raise ValueError("Avatar ID is None. Cannot update parent store.")

        # Update the parent store with values from this subflow
        await parent_store.set_avatar_id(avatar_subflow_state.avatar_id)
