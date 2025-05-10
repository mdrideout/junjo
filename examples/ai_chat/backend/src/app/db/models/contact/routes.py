from fastapi import APIRouter
from loguru import logger

from app.db.models.contact.repository import ContactRepository
from app.db.models.contact.schemas import ContactRead
from app.db.queries.create_setup_contact.schemas import CreateSetupContactResponse
from app.workflows.create_contact.workflow import run_create_contact_workflow

contact_router = APIRouter(prefix="/api/contact")


@contact_router.post("/")
async def post_contact() -> CreateSetupContactResponse:
    """
    Create a contact.
    """
    logger.info("Creating a contact")

    # Execute the create contact workflow
    new_contact = await run_create_contact_workflow()

    return new_contact



@contact_router.get("/")
async def get_contacts() -> list[ContactRead]:
    """
    Get all contacts.
    """
    logger.info("Getting all contacts")

    result = await ContactRepository.read_all()
    return result

@contact_router.delete("/{contact_id}")
async def delete_contact(contact_id: int) -> None:
    """
    Delete a contact

    This will cascade delete the chat, messages, and chat_members
    """
    raise NotImplementedError("Not implemented")
