# app/db/models/chat_members/routes.py

from fastapi import APIRouter, HTTPException
from loguru import logger

from app.db.models.chat_members.repository import ChatMembersRepository
from app.db.models.chat_members.schemas import ChatMemberCreate, ChatMemberRead

chat_members_router = APIRouter(prefix="/api/chat_member")


@chat_members_router.post("/")
async def post_chat_member(request: ChatMemberCreate) -> ChatMemberRead:
    """
    Create a new chat member (add to group chat)
    """
    logger.info(f"Creating new chat member with request: {request}")

    try:
        # Call the repository service to create the chat member
        result = await ChatMembersRepository.create(request)

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@chat_members_router.get("/chat/{chat_id}")
async def get_chat_members_by_chat_id(chat_id: str) -> list[ChatMemberRead]:
    """
    Get all members of a specific chat
    """
    logger.info(f"Getting chat members by chat id: {chat_id}")

    result = await ChatMembersRepository.read_by_chat_id(chat_id)
    return result
