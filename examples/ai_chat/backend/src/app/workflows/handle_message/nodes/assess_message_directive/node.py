from junjo.node import Node
from loguru import logger

from app.ai_services.gemini.gemini_tool import GeminiTool
from app.workflows.handle_message.nodes.assess_message_directive.prompt_gemini import (
    assess_message_directive_prompt,
)
from app.workflows.handle_message.schemas import MessageDirective
from app.workflows.handle_message.store import MessageWorkflowStore


class AssessMessageDirectiveNode(Node[MessageWorkflowStore]):
    """Assess the message directive based on the conversation history."""

    async def service(self, store) -> None:
        state = await store.get_state()

        # Construct the prompt
        prompt = assess_message_directive_prompt(state.conversation_history)
        logger.info(f"Prompt: {prompt}")

        # Create a request to gemini
        gemini_tool = GeminiTool(prompt=prompt, model="gemini-2.0-flash-001")
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
