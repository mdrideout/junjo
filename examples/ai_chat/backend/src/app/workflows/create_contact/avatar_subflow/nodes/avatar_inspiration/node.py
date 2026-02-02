from junjo.node import Node
from loguru import logger

from app.ai_services.grok import GrokTool
from app.workflows.create_contact.avatar_subflow.nodes.avatar_inspiration.prompt import avatar_inspiration_prompt
from app.workflows.create_contact.avatar_subflow.store import AvatarSubflowStore


class AvatarInspirationNode(Node[AvatarSubflowStore]):
    """
    Node for creating the inspiration for an avatar for a contact.
    """

    async def service(self, store: AvatarSubflowStore) -> None:
        """
        Service method to create the inspiration for an avatar for a contact.
        """

        state = await store.get_state()
        parent_state = state.parent_state

        if parent_state is None:
            raise ValueError("parent_state is required for this node.")

        if parent_state.personality_traits is None:
            raise ValueError("personality_traits are required for this node.")

        if parent_state.location is None:
            raise ValueError("location is required for this node.")

        if parent_state.bio is None:
            raise ValueError("bio is required for this node.")

        first_name = "first_name here"

        last_name = "last_name here"

        # Create the request to gemini for avatar inspiration
        prompt = avatar_inspiration_prompt(
            parent_state.personality_traits,
            parent_state.bio,
            parent_state.location.city,
            parent_state.location.state,
            first_name,
            last_name,
        )
        logger.info(f"Creating response with prompt: {prompt}")

        grok_tool = GrokTool(prompt=prompt, model="grok-4-1-fast-non-reasoning")
        grok_result = await grok_tool.text_request()
        logger.info(f"Grok result: {grok_result}")

        # Update the state with the avatar id
        await store.set_inspiration_prompt(grok_result)

        return
