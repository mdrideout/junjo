from fastapi import APIRouter
from loguru import logger

from app.contact.repository import ContactRepository
from app.contact.schemas import ContactCreate, ContactRead

contact_router = APIRouter(prefix="/contact")

@contact_router.post("/")
async def post_contact(
  request: ContactCreate
) -> ContactRead:
  """
  Create a new contact
  """

  logger.info(f"Creating new contact with request: {request}")

  # Call the repository service to create the contact
  result = await ContactRepository.create(request)

  return result
