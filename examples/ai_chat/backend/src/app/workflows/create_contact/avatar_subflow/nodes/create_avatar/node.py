from junjo.node import Node
from loguru import logger
from nanoid import generate

from app.ai_services.grok import GrokTool
from app.util.save_image_file import save_image_file
from app.workflows.create_contact.avatar_subflow.nodes.create_avatar.prompt import create_avatar_prompt
from app.workflows.create_contact.avatar_subflow.store import AvatarSubflowStore


class CreateAvatarNode(Node[AvatarSubflowStore]):
    """
    Node for creating an avatar for a contact.
    """

    async def service(self, store: AvatarSubflowStore) -> None:
        """
        Service method to create an avatar for a contact.
        """

        # Get the current state
        state = await store.get_state()

        if state.parent_state is None:
            raise ValueError("parent_state is required for this node.")

        # Check for required store data
        if state.parent_state.personality_traits is None:
            raise ValueError("personality_traits are required for this node.")

        if state.parent_state.bio is None:
            raise ValueError("bio is required for this node.")

        if state.parent_state.location is None:
            raise ValueError("location is required for this node.")

        if state.parent_state.sex is None:
            raise ValueError("sex is required for this node.")

        if state.inspiration_prompt is None:
            raise ValueError("inspiration_prompt is required for this node.")

        # Construct the prompt
        prompt = create_avatar_prompt(
            state.parent_state.personality_traits,
            state.parent_state.bio,
            state.parent_state.location.city,
            state.parent_state.location.state,
            state.parent_state.sex,
            state.inspiration_prompt,
        )
        logger.info(f"Creating image with prompt: {prompt}")

        grok_tool = GrokTool(prompt=prompt, model="grok-imagine-image")
        image_bytes = await grok_tool.image_request()
        logger.info(f"Grok result image size: {len(image_bytes) / 1024} kb")

        # Create an id for the avatar
        avatar_id = generate()

        # Save the image to the file system
        save_image_file(image_bytes, "avatars", avatar_id, "png")

        # Update the state with the avatar id
        await store.set_avatar_id(avatar_id)

        return
