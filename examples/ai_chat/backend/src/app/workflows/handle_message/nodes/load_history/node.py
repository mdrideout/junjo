from junjo.node import Node

from app.db.models.message.services import MessageService
from app.workflows.handle_message.store import MessageWorkflowStore


class LoadHistoryNode(Node[MessageWorkflowStore]):
    """Load conversation history from the database and set it to state."""

    async def service(self, store) -> None:
        state = await store.get_state()

        # Load the conversation history from the database
        history = await MessageService.get_chat_messages(state.received_message.chat_id)

        # print(f"Fetched history: {history}")

        # Set the conversation history to state
        await store.set_conversation_history(history)

        return
