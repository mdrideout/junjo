from junjo.node import Node
from loguru import logger
from nanoid import generate

from app.ai_services.gemini.gemini_tool import GeminiTool
from app.util.get_image_bytes import get_image_bytes
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

        # Get the contact from the parent state
        contact = state.parent_state.contact
        if contact is None:
            raise ValueError("Contact is required to execute this node.")

        # Get the avatar image bytes
        avatar_image_bytes = get_image_bytes("avatars", contact.avatar_id, "png")

        # Create a request to gemini
        gemini_tool = GeminiTool(prompt=prompt, model="gemini-2.5-flash-image-preview")
        image_bytes, text_response = await gemini_tool.gemini_image_edit_request(avatar_image_bytes)

        if image_bytes:
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

        if text_response:
            await store.set_text_response(text_response)

        return
