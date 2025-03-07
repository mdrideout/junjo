from app.db.models.message.repository import MessageRepository
from app.db.models.message.schemas import MessageCreate, MessageRead


class MessageService:
    """Service layer for message related business logic."""

    @staticmethod
    async def save_message(message: MessageCreate) -> MessageRead:
        """Business logic to handle saving the message to the database."""

        saved_message = await MessageRepository.create(message)

        return saved_message

    @staticmethod
    async def get_chat_messages(chat_id: str) -> list[MessageRead]:
        """Business logic to handle getting chat messages from the database."""

        messages = await MessageRepository.read_all_by_chat_id(chat_id)

        return messages
