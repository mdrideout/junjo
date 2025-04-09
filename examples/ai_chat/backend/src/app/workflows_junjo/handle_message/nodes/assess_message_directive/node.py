from junjo.node import Node
from loguru import logger

from app.ai_services.gemini.gemini_tool import GeminiTool
from app.workflows_junjo.handle_message.nodes.assess_message_directive.prompt_gemini import (
    assess_message_directive_prompt,
)
from app.workflows_junjo.handle_message.schemas import MessageDirective
from app.workflows_junjo.handle_message.store import MessageWorkflowStore


class AssessMessageDirectiveNode(Node[MessageWorkflowStore]):
    """Assess the message directive based on the user's message."""

    async def service(self, store) -> None:
        state = await store.get_state()

        received_message = state.received_message
        if received_message is None:
            raise ValueError("received_message is required to execute this node.")

        # Construct the prompt
        prompt = assess_message_directive_prompt(received_message.message)
        logger.info(f"Prompt: {prompt}")

        # Create a request to gemini
        gemini_tool = GeminiTool(prompt=prompt, model="gemini-1.5-flash-8b-001")
        gemini_result = await gemini_tool.text_request()
        logger.info(f"Gemini result: {gemini_result}")

        # Validate the result is a MessageDirective enum
        if not gemini_result:
            raise ValueError("Gemini result is empty.")

        try:
            # Attempt to construct the enum value with the gemini_result
            message_directive = MessageDirective(gemini_result)
        except ValueError as e:
            raise ValueError(f"Gemini result '{gemini_result}' is not a valid MessageDirective.") from e

        # Update state
        await store.set_message_directive(message_directive)

        return
