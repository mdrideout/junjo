from junjo.node import Node
from loguru import logger

from app.ai_services.grok import GrokTool
from app.workflows.handle_message.create_response_with_image_subflow.nodes.image_inspiration.prompt import (
    image_inspiration_prompt,
)
from app.workflows.handle_message.create_response_with_image_subflow.store import (
    CreateResponseWithImageSubflowStore,
)


class ImageInspirationNode(Node[CreateResponseWithImageSubflowStore]):
    """
    Node for creating the inspiration for an image to be included in a chat response.
    """

    async def service(self, store: CreateResponseWithImageSubflowStore) -> None:
        """
        Service method to create the inspiration for an image.
        """

        state = await store.get_state()
        parent_state = state.parent_state

        if parent_state is None:
            raise ValueError("parent_state is required for this node.")

        if parent_state.contact is None:
            raise ValueError("Contact is required to execute this node.")

        # Create the request to gemini for image inspiration
        prompt = image_inspiration_prompt(parent_state.conversation_history, parent_state.contact)
        logger.info(f"Creating response with prompt: {prompt}")

        grok_tool = GrokTool(prompt=prompt, model="grok-4-1-fast-non-reasoning")
        grok_result = await grok_tool.text_request()
        logger.info(f"Grok result: {grok_result}")

        # Update the state with the image id
        await store.set_inspiration_prompt(grok_result)

        return
