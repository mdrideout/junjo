from junjo.node import Node
from loguru import logger

from app.db.models.contact.services import ContactService
from app.workflows_junjo.handle_message.store import MessageWorkflowStore


class LoadContactNode(Node[MessageWorkflowStore]):
    """Load conversation contact from the database and set it to state."""

    async def service(self, store) -> None:
        state = await store.get_state()

        logger.info("Fetching contact for state...")

        # Load the conversation contact from the database
        contact = await ContactService.get_chat_contact(state.received_message.chat_id)

        logger.info(f"Fetched contact: {contact}")

        # Set the conversation contact to state
        await store.set_contact(self, contact)

        return
