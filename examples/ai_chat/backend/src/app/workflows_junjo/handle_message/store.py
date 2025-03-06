
from junjo.store import BaseStore, immutable_update
from pydantic import BaseModel

from app.db.models.contact.schemas import ContactRead
from app.db.models.message.schemas import MessageCreate, MessageRead


class MessageWorkflowState(BaseModel):
    received_message: MessageCreate
    conversation_history: list[MessageRead] = []
    contact: ContactRead | None = None
    response_message: MessageCreate | None = None




class MessageWorkflowStore(BaseStore[MessageWorkflowState]):
    """
    A concrete store for MessageWorkflowState.
    """

    @immutable_update
    def set_conversation_history(self, payload: list[MessageRead]) -> MessageWorkflowState:
        return self._state.model_copy(update={"conversation_history": payload})

    @immutable_update
    def append_conversation_history(self, payload: MessageRead) -> MessageWorkflowState:
        return self._state.model_copy(update={"conversation_history": [*self._state.conversation_history, payload]})

    @immutable_update
    def set_received_message(self, payload: MessageCreate) -> MessageWorkflowState:
        return self._state.model_copy(update={"received_message": payload})

    @immutable_update
    def set_contact(self, payload: ContactRead) -> MessageWorkflowState:
        return self._state.model_copy(update={"contact": payload})

