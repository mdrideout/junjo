from junjo.node import Node
from loguru import logger

from app.ai_services.gemini.gemini_tool import GeminiTool
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

        # Create the request to gemini for image inspiration
        prompt = image_inspiration_prompt(
            parent_state.conversation_history,
        )
        logger.info(f"Creating response with prompt: {prompt}")

        # Create a request to gemini
        gemini_tool = GeminiTool(prompt=prompt, model="gemini-2.5-flash")
        gemini_result = await gemini_tool.text_request()
        logger.info(f"Gemini result: {gemini_result}")

        # Update the state with the image id
        await store.set_inspiration_prompt(gemini_result)

        return
