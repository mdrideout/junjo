import asyncio

from fastapi import APIRouter
from loguru import logger

from app.db.models.message.schemas import MessageCreate
from app.workflows_junjo.handle_message.workflow import handle_message_workflow

workflows_junjo_router = APIRouter(prefix="/workflows-junjo")


# @workflows_junjo_router.post("/contact")
# async def post_contact_workflow(request: ContactCreateWorkflowRequest) -> CreateSetupContactResponse:
#     """
#     Create a new contact via the LLM workflow.
#     """

#     logger.info("Creating new contact via LLM workflow")

#     # Create schema as a string
#     json_schema = ContactCreate.model_json_schema(mode="serialization")
#     schema_string = json.dumps(json_schema)
#     prompt = contact_create_prompt_gemini(schema_string, request.gender)

#     # Create a request to gemini
#     gemini_tool = GeminiTool(prompt=prompt, model="gemini-1.5-flash-8b-001")
#     gemini_result = await gemini_tool.schema_request(ContactCreate)
#     logger.info(f"Gemini result: {gemini_result}")

#     # Convert it to the ContactCreate model
#     create_model = ContactCreate.model_validate(gemini_result)

#     # Insert it into the database
#     result = await CreateSetupContactRepository.create_setup_contact(create_model)

#     return result


@workflows_junjo_router.post("/handle-message/{chat_id}")
async def post_message_workflow(request: MessageCreate) -> None:
    """
    Kick off the junjo handle message workflow
    """
    logger.info("Request: Junjo handle_message workflow")

    # Kick off the workflow in a background task:
    asyncio.create_task(handle_message_workflow(request))

    return


