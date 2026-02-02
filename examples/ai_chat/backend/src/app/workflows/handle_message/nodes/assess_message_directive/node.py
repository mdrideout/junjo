from junjo.node import Node
from loguru import logger

from app.ai_services.grok import GrokTool
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

        grok_tool = GrokTool(prompt=prompt, model="grok-4-1-fast-non-reasoning")
        grok_result = await grok_tool.text_request()
        logger.info(f"Grok result: {grok_result}")

        # Validate the result is a MessageDirective enum
        if not grok_result:
            raise ValueError("Grok result is empty.")

        try:
            message_directive = MessageDirective(grok_result)
        except ValueError as e:
            raise ValueError(f"Grok result '{grok_result}' is not a valid MessageDirective.") from e

        # Update state
        await store.set_message_directive(message_directive)

        return
