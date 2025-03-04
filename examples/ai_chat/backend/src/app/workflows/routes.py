import json

from fastapi import APIRouter
from loguru import logger

from app.ai_services.gemini.gemini_tool import GeminiTool
from app.db.models.contact.schemas import ContactCreate
from app.db.models.message.repository import MessageRepository
from app.db.models.message.schemas import MessageCreate, MessageRead
from app.db.queries.create_setup_contact.repository import CreateSetupContactRepository
from app.db.queries.create_setup_contact.schemas import CreateSetupContactResponse
from app.workflows.contact_create.prompt_gemini import contact_create_prompt_gemini
from app.workflows.contact_create.schemas import ContactCreateWorkflowRequest

workflows_router = APIRouter(prefix="/workflows")


@workflows_router.post("/contact")
async def post_contact_workflow(request: ContactCreateWorkflowRequest) -> CreateSetupContactResponse:
    """
    Create a new contact via the LLM workflow.
    """

    logger.info("Creating new contact via LLM workflow")

    # Create schema as a string
    json_schema = ContactCreate.model_json_schema(mode="serialization")
    schema_string = json.dumps(json_schema)
    prompt = prompt=contact_create_prompt_gemini(schema_string, request.gender)

    # Test the gemini request
    gemini_tool = GeminiTool(prompt=prompt, model="gemini-1.5-flash-8b-001")
    gemini_result = await gemini_tool.schema_request(ContactCreate)
    logger.info(f"Gemini result: {gemini_result}")

    # Convert it to the ContactCreate model
    create_model = ContactCreate.model_validate(gemini_result)

    # Insert it into the database
    result = await CreateSetupContactRepository.create_setup_contact(create_model)

    return result


@workflows_router.post("/send-message/{chat_id}")
async def post_message_workflow(request: MessageCreate) -> MessageRead:
    """
    Create a new message via the LLM workflow.
    """

    logger.info("Creating new message via LLM workflow")

    # Insert user's message into DB
    user_message = await MessageRepository.create(request)

    # TODO: Trigger workflow
    # TODO: Client polls for updates to the chat_id

    return user_message

