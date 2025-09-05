from junjo.state import BaseState
from junjo.store import BaseStore

from app.workflows.handle_message.store import MessageWorkflowState


class CreateResponseWithImageSubflowState(BaseState):
    # Input State - this subflow will be constructed with this initial state
    parent_state: MessageWorkflowState | None = None

    # Output State - will be generated in this subflow
    inspiration_prompt: str | None = None
    image_id: str | None = None


class CreateResponseWithImageSubflowStore(BaseStore[CreateResponseWithImageSubflowState]):
    """
    A concrete store for CreateResponseWithImageSubflowState.
    """

    async def set_parent_state(self, payload: MessageWorkflowState) -> None:
        await self.set_state({"parent_state": payload})

    async def set_inspiration_prompt(self, payload: str) -> None:
        await self.set_state({"inspiration_prompt": payload})

    async def set_image_id(self, payload: str) -> None:
        await self.set_state({"image_id": payload})
