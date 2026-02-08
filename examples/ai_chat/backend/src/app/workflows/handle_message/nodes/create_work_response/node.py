from junjo.node import Node
from loguru import logger

from app.ai_services.grok import GrokTool
from app.db.models.message.repository import MessageRepository
from app.db.models.message.schemas import MessageCreate
from app.workflows.handle_message.nodes.create_work_response.prompt_gemini import (
    create_work_response_workflow_prompt,
)
from app.workflows.handle_message.store import MessageWorkflowStore


class CreateWorkResponseNode(Node[MessageWorkflowStore]):
    """Create a work response message based on the data loaded into state."""

    async def service(self, store) -> None:
        state = await store.get_state()

        contact = state.contact
        if contact is None:
            raise ValueError("Contact is required to execute this node.")

        # Construct the prompt
        prompt = create_work_response_workflow_prompt(
            state.conversation_history, contact, state.received_message.message
        )
        logger.info(f"Prompt: {prompt}")

        grok_tool = GrokTool(prompt=prompt, model="grok-4-1-fast-non-reasoning")
        grok_result = await grok_tool.text_request()
        logger.info(f"Grok result: {grok_result}")

        # Create a message for the database
        message_create = MessageCreate(
            chat_id=state.received_message.chat_id, contact_id=contact.id, message=grok_result
        )

        # Insert the message into the database
        response = await MessageRepository.create(message_create)

        # Update state
        await store.set_response_message(response)

        return
