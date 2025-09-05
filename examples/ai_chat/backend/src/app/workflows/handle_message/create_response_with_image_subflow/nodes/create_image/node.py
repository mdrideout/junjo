from junjo.node import Node
from loguru import logger
from nanoid import generate

from app.ai_services.gemini.gemini_tool import GeminiTool
from app.util.save_image_file import save_image_file
from app.workflows.handle_message.create_response_with_image_subflow.store import (
    CreateResponseWithImageSubflowStore,
)


class CreateImageNode(Node[CreateResponseWithImageSubflowStore]):
    """
    Node for creating an image to be included in a chat response.
    """

    async def service(self, store: CreateResponseWithImageSubflowStore) -> None:
        """
        Service method to create an image.
        """

        # Get the current state
        state = await store.get_state()

        if state.parent_state is None:
            raise ValueError("parent_state is required for this node.")

        # Check for required store data
        if state.inspiration_prompt is None:
            raise ValueError("inspiration_prompt is required for this node.")

        # Construct the prompt
        prompt = state.inspiration_prompt
        logger.info(f"Creating image with prompt: {prompt}")

        # Create a request to gemini
        gemini_tool = GeminiTool(prompt=prompt, model="gemini-1.5-pro")
        image_bytes = await gemini_tool.gemini_image_request()
        logger.info(f"Gemini result image size: {len(image_bytes) / 1024} kb")

        # Create an id for the image
        image_id = generate()

        # Save the image to the file system
        save_image_file(
            image_bytes,
            f"chat-images/{state.parent_state.received_message.chat_id}",
            image_id,
            "png",
        )

        # Update the state with the image id
        await store.set_image_id(image_id)

        return
