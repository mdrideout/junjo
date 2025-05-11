
from junjo import BaseState, BaseStore

from app.db.models.contact.schemas import ContactRead
from app.db.models.message.schemas import MessageCreate, MessageRead
from app.workflows.handle_message.schemas import MessageDirective


class MessageWorkflowState(BaseState):
    received_message: MessageCreate
    message_directive: MessageDirective | None = None
    conversation_history: list[MessageRead] = []
    contact: ContactRead | None = None
    response_message: MessageRead | None = None
    concurrent_update_test_state: str | None = None
    sub_flow_jokes: list[str] = []
    sub_sub_flow_facts: list[str] = []

class MessageWorkflowStore(BaseStore[MessageWorkflowState]):
    """
    A concrete store for MessageWorkflowState.
    """

    async def set_received_message(self, payload: MessageCreate) -> None:
        await self.set_state({"received_message": payload})

    async def set_message_directive(self, payload: MessageDirective) -> None:
        await self.set_state({"message_directive": payload})

    async def set_conversation_history(self, payload: list[MessageRead]) -> None:
        await self.set_state({"conversation_history": payload})

    async def append_conversation_history(self, payload: MessageRead) -> None:
        await self.set_state({"conversation_history": [*self._state.conversation_history, payload]})

    async def set_contact(self, payload: ContactRead) -> None:
        await self.set_state({"contact": payload})

    async def set_response_message(self, payload: MessageRead) -> None:
        await self.set_state({"response_message": payload})

    async def set_concurrent_update_test_state(self, payload: str) -> None:
        await self.set_state({"concurrent_update_test_state": payload})

    async def set_sub_flow_jokes(self, payload: list[str]) -> None:
        await self.set_state({"sub_flow_jokes": payload})

    async def set_sub_sub_flow_facts(self, payload: list[str]) -> None:
        await self.set_state({"sub_sub_flow_facts": payload})


