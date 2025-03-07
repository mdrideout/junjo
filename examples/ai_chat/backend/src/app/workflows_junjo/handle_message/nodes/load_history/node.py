from junjo.node import Node
from loguru import logger

from app.db.models.message.services import MessageService
from app.workflows_junjo.handle_message.store import MessageWorkflowStore


class LoadHistoryNode(Node[MessageWorkflowStore]):
    """Load conversation history from the database and set it to state."""

    async def service(self, store: MessageWorkflowStore) -> None:
        state = store.get_state()

        # Load the conversation history from the database
        history = await MessageService.get_chat_messages(state.received_message.chat_id)

        logger.info(f"Fetched history: {history}")

        # Set the conversation history to state
        store.set_conversation_history(history)

        return
