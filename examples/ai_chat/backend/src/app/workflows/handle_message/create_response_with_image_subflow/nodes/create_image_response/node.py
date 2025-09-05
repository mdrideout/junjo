from junjo.node import Node
from loguru import logger

from app.db.models.message.repository import MessageRepository
from app.db.models.message.schemas import MessageCreate
from app.workflows.handle_message.create_response_with_image_subflow.store import (
    CreateResponseWithImageSubflowStore,
)


class CreateImageResponseNode(Node[CreateResponseWithImageSubflowStore]):
    """Create a response message based on the data loaded into state."""

    async def service(self, store: CreateResponseWithImageSubflowStore) -> None:
        state = await store.get_state()
        parent_state = state.parent_state

        if parent_state is None:
            raise ValueError("parent_state is required for this node.")

        contact = parent_state.contact
        if contact is None:
            raise ValueError("Contact is required to execute this node.")

        if state.image_id is None:
            raise ValueError("Image ID is required to execute this node.")

        # Create a message for the database
        message_create = MessageCreate(
            chat_id=parent_state.received_message.chat_id,
            contact_id=contact.id,
            message=f"Image response: {state.image_id}",
            image_id=state.image_id,
        )

        # Insert the message into the database
        response = await MessageRepository.create(message_create)
        logger.info(f"Created message with image: {response}")

        return
