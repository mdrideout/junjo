
from junjo.state import BaseState
from junjo.store import BaseStore

from app.workflows.create_contact.store import CreateContactState


class AvatarSubflowState(BaseState):
    # Input State - this subflow will be constructed with this initial state
    parent_state: CreateContactState | None = None

    # Output State - will be generated in this subflow
    inspiration_prompt: str | None = None
    avatar_id: str | None = None


class AvatarSubflowStore(BaseStore[AvatarSubflowState]):
    """
    A concrete store for AvatarSubflowState.
    """

    async def set_parent_state(self, payload: CreateContactState) -> None:
        await self.set_state({"parent_state": payload})

    async def set_inspiration_prompt(self, payload: str) -> None:
        await self.set_state({"inspiration_prompt": payload})

    async def set_avatar_id(self, payload: str) -> None:
        await self.set_state({"avatar_id": payload})

