from fastapi import APIRouter
from loguru import logger

from app.db.models.contact.repository import ContactRepository
from app.db.models.contact.schemas import ContactCreate, ContactRead

contact_router = APIRouter(prefix="/api/contact")


@contact_router.post("/")
async def post_contact(request: ContactCreate) -> ContactRead:
    """
    Create a new contact directly.
    """

    logger.info(f"Creating new contact with request: {request}")

    # Call the repository service to create the contact
    result = await ContactRepository.create(request)

    return result

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
