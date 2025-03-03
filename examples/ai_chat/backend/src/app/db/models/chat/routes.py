# app/db/models/chat/routes.py

from fastapi import APIRouter, HTTPException
from loguru import logger

from app.db.models.chat.repository import ChatRepository
from app.db.models.chat.schemas import ChatRead, ChatWithMembersRead

chat_router = APIRouter(prefix="/api/chat")


@chat_router.post("/")
async def post_chat() -> ChatRead:
    """
    Create a new chat.
    """
    logger.info("Creating new chat")

    try:
        # Call the repository service to create the chat
        result = await ChatRepository.create()

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@chat_router.get("/")
async def get_chats() -> list[ChatRead]:
    """
    Get all chats.
    """
    logger.info("Getting all chats")

    result = await ChatRepository.read_all()
    return result

@chat_router.get("/with-members")
async def get_chats_with_members() -> list[ChatWithMembersRead]:
    """
    Get all chats with their members.
    """
    logger.info("Getting all chats with their members")
    result = await ChatRepository.read_all_with_members()
    return result


@chat_router.get("/{chat_id}")
async def get_chat(chat_id: str) -> ChatRead:
    """
    Get a specific chat.
    """
    logger.info(f"Getting chat {chat_id}")

    result = await ChatRepository.read(chat_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Chat with id: {chat_id} not found")
    return result

