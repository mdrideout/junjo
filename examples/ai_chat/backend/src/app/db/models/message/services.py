from app.db.models.message.repository import MessageRepository
from app.db.models.message.schemas import MessageCreate, MessageRead


class MessageService:
    """Service layer for message related business logic."""

    @staticmethod
    async def save_message(message: MessageCreate) -> MessageRead:
        """Business logic to handle saving the message to the database."""

        saved_message = await MessageRepository.create(message)

        return saved_message
