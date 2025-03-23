
from junjo.node import Node
from junjo.state import BaseState
from junjo.store import BaseStore

from app.db.models.contact.schemas import ContactRead
from app.db.models.message.schemas import MessageCreate, MessageRead


class MessageWorkflowState(BaseState):
    received_message: MessageCreate
    conversation_history: list[MessageRead] = []
    contact: ContactRead | None = None
    response_message: MessageRead | None = None


class MessageWorkflowStore(BaseStore[MessageWorkflowState]):
    """
    A concrete store for MessageWorkflowState.
    """

    async def set_conversation_history(self, node: Node, payload: list[MessageRead]) -> None:
        await self.set_state(node, {"conversation_history": payload})

    async def append_conversation_history(self, node: Node, payload: MessageRead) -> None:
        await self.set_state(node, {"conversation_history": [*self._state.conversation_history, payload]})

    async def set_received_message(self, node: Node, payload: MessageCreate) -> None:
        await self.set_state(node, {"received_message": payload})

    async def set_contact(self, node: Node, payload: ContactRead) -> None:
        await self.set_state(node, {"contact": payload})

    async def set_response_message(self, node: Node, payload: MessageRead) -> None:
        await self.set_state(node, {"response_message": payload})

