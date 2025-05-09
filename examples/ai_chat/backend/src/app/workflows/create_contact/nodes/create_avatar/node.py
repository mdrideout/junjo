
from junjo.node import Node
from loguru import logger
from nanoid import generate

from app.ai_services.gemini.gemini_tool import GeminiTool
from app.util.save_image_file import save_image_file
from app.workflows.create_contact.nodes.create_avatar.prompt import create_avatar_prompt
from app.workflows.create_contact.store import CreateContactStore


class CreateAvatarNode(Node[CreateContactStore]):
    """
    Node for creating an avatar for a contact.
    """

    async def service(self, store: CreateContactStore) -> None:
        """
        Service method to create an avatar for a contact.
        """

        # Get the current state
        state = await store.get_state()

        # Check for required store data
        if state.personality_traits is None:
            raise ValueError("personality_traits are required for this node.")

        # if state.bio is None:
        #     raise ValueError("bio is required for this node.")

        if state.location is None:
            raise ValueError("location is required for this node.")

        # Construct the prompt
        prompt = create_avatar_prompt(state.personality_traits, "bio here", state.location.city, state.location.state)
        logger.info(f"Creating image with prompt: {prompt}")

        # Create a request to gemini
        gemini_tool = GeminiTool(prompt=prompt, model="gemini-2.0-flash-preview-image-generation")
        image_bytes = await gemini_tool.gemini_image_request()
        logger.info(f"Gemini result image size: {len(image_bytes) / 1024} kb")

        # Create an id for the avatar
        avatar_id = generate()

        # Save the image to the file system
        save_image_file(image_bytes, "avatars", avatar_id, "png")

        # Update the state with the avatar id
        await store.set_avatar_id(avatar_id)

        return
