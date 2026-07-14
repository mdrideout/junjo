"""Awaited request/response routes with no polling or background execution."""

from fastapi import APIRouter, Request

from ai_chat.bootstrap import ChatApplication

from .schemas import (
    ConversationListResponse,
    ConversationSummary,
    MessageListResponse,
    MessageResponse,
    SubmitTurnRequest,
    SubmitTurnResponse,
)

router = APIRouter(prefix="/api")


def _application(request: Request) -> ChatApplication:
    application = request.app.state.chat_application
    if not isinstance(application, ChatApplication):
        raise RuntimeError("Chat application state is not configured.")
    return application


@router.get("/conversations")
async def list_conversations(request: Request) -> ConversationListResponse:
    conversations = await _application(request).list_conversations()
    return ConversationListResponse(
        conversations=tuple(ConversationSummary.from_domain(item) for item in conversations)
    )


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: str, request: Request) -> MessageListResponse:
    messages = await _application(request).list_messages(conversation_id)
    return MessageListResponse(
        conversation_id=conversation_id,
        messages=tuple(MessageResponse.from_domain(item) for item in messages),
    )


@router.post("/conversations/{conversation_id}/turns")
async def submit_turn(
    conversation_id: str,
    body: SubmitTurnRequest,
    request: Request,
) -> SubmitTurnResponse:
    result = await _application(request).turns.submit(
        conversation_id=conversation_id,
        text=body.text,
    )
    return SubmitTurnResponse.from_domain(result)
