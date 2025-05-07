import asyncio

from fastapi import APIRouter
from loguru import logger

from app.db.models.message.schemas import MessageCreate
from app.workflows.handle_message.workflow import run_handle_message_workflow

workflows_junjo_router = APIRouter(prefix="/workflows-junjo")

@workflows_junjo_router.post("/handle-message/{chat_id}")
async def post_message_workflow(request: MessageCreate) -> None:
    """
    Kick off the junjo handle message workflow
    """
    logger.info("Request: Junjo handle_message workflow")

    # Kick off the workflow in a background task:
    asyncio.create_task(run_handle_message_workflow(request))

    return


