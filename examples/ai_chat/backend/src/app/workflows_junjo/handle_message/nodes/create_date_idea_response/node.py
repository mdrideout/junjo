from junjo.node import Node
from loguru import logger

from app.ai_services.gemini.gemini_tool import GeminiTool
from app.db.models.message.repository import MessageRepository
from app.db.models.message.schemas import MessageCreate
from app.workflows_junjo.handle_message.store import MessageWorkflowStore
from app.workflows_junjo.handle_message.nodes.create_date_idea_response.prompt_gemini import create_date_idea_response_workflow_prompt

class CreateDateIdeaResponseNode(Node[MessageWorkflowStore]):
    """Create a date idea response message based on the data loaded into state."""

    async def service(self, store) -> None:
        state = await store.get_state()

        contact = state.contact
        if contact is None:
            raise ValueError("Contact is required to execute this node.")

        # Construct the prompt
        prompt = create_date_idea_response_workflow_prompt(state.conversation_history, contact, state.received_message.message)
        logger.info(f"Prompt: {prompt}")

        # Create a request to gemini
        gemini_tool = GeminiTool(prompt=prompt, model="gemini-1.5-flash-8b-001")
        gemini_result = await gemini_tool.text_request()
        logger.info(f"Gemini result: {gemini_result}")

        # Create a message for the database
        message_create = MessageCreate(
            chat_id=state.received_message.chat_id,
            contact_id=contact.id,
            message=gemini_result
        )

        # Insert the message into the database
        response = await MessageRepository.create(message_create)

        # Update state
        await store.set_response_message(self, response)

        return
