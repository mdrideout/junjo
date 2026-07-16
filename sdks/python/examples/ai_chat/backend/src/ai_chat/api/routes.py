"""Turn-oriented routes over application-owned background execution."""

from fastapi import APIRouter, Request, Response, status

from ai_chat.bootstrap import ChatApplication

from .schemas import (
    ConversationListResponse,
    ConversationSummary,
    CreateContactRequest,
    CreateContactResponse,
    PublicConfigResponse,
    SubmitTurnRequest,
    TurnListResponse,
    TurnResponse,
)

router = APIRouter(prefix="/api")


def _application(request: Request) -> ChatApplication:
    application = request.app.state.chat_application
    if not isinstance(application, ChatApplication):
        raise RuntimeError("Chat application state is not configured.")
    return application


@router.get("/healthz", include_in_schema=False, status_code=status.HTTP_204_NO_CONTENT)
async def health(request: Request) -> Response:
    """Report readiness only after the application lifespan has initialized."""

    _application(request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/config")
async def public_config(request: Request) -> PublicConfigResponse:
    return PublicConfigResponse.from_settings(_application(request).debug)


@router.get("/conversations")
async def list_conversations(request: Request) -> ConversationListResponse:
    conversations = await _application(request).list_conversations()
    return ConversationListResponse(
        conversations=tuple(ConversationSummary.from_domain(item) for item in conversations)
    )


@router.get("/conversations/{conversation_id}/turns")
async def list_turns(conversation_id: str, request: Request) -> TurnListResponse:
    turns = await _application(request).list_turns(conversation_id)
    return TurnListResponse(
        conversation_id=conversation_id,
        turns=tuple(TurnResponse.from_domain(item) for item in turns),
    )


@router.get("/turns/{turn_id}")
async def get_turn(turn_id: str, request: Request) -> TurnResponse:
    turn = await _application(request).store.get_turn(turn_id)
    return TurnResponse.from_domain(turn)


@router.post("/contacts", status_code=status.HTTP_201_CREATED)
async def create_contact(
    body: CreateContactRequest,
    request: Request,
) -> CreateContactResponse:
    result = await _application(request).contacts.create(body.sex)
    return CreateContactResponse(conversation=ConversationSummary.from_domain(result))


@router.post(
    "/conversations/{conversation_id}/turns",
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_turn(
    conversation_id: str,
    body: SubmitTurnRequest,
    request: Request,
) -> TurnResponse:
    turn = await _application(request).admit_turn(
        conversation_id=conversation_id,
        text=body.text,
    )
    return TurnResponse.from_domain(turn)
