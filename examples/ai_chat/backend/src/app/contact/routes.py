from fastapi import APIRouter
from loguru import logger

from app.ai.gemini.gemini_tool import GeminiTool
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

  # Test the gemini request
  gemini_tool = GeminiTool(
    prompt="Write a joke about dating apps.",
    model="gemini-2.0-flash-lite-001"
  )
  gemini_result = await gemini_tool.text_request()
  logger.info(f"Gemini result: {gemini_result}")


  # Call the repository service to create the contact
  result = await ContactRepository.create(request)

  return result
