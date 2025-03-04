from fastapi import APIRouter, HTTPException
from loguru import logger

from app.db.models.message.repository import MessageRepository
from app.db.models.message.schemas import MessageCreate, MessageRead

message_router = APIRouter(prefix="/api/message")


@message_router.post("/")
async def post_message(request: MessageCreate) -> MessageRead:
    """
    Create a new message directly.
    """

    logger.info(f"Creating new message with request: {request}")

    try:
        # Call the repository service to create the message
        result = await MessageRepository.create(request)

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@message_router.get("/")
async def get_messages() -> list[MessageRead]:
    """
    Get all messages.
    """
    logger.info("Getting all messages")

    result = await MessageRepository.read_all()
    return result

@message_router.get("/{chat_id}")
async def get_messages_for_chat(chat_id: str) -> list[MessageRead]:
    """
    Get all messages for a chat.
    """
    logger.info(f"Getting all messages for chat {chat_id}")

    result = await MessageRepository.read_all_by_chat_id(chat_id)
    return result
