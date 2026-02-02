from junjo.node import Node
from loguru import logger

from app.ai_services.grok import GrokTool
from app.workflows.create_contact.nodes.create_name.prompt import create_name_prompt
from app.workflows.create_contact.nodes.create_name.schema import CreateNameSchema
from app.workflows.create_contact.store import CreateContactStore


class CreateNameNode(Node[CreateContactStore]):
    """
    Node for creating the name for a contact.
    """

    async def service(self, store: CreateContactStore) -> None:
        """
        Service method to create the name for a contact.
        """

        # Get the current state
        state = await store.get_state()

        # Null check the state data for the prompt
        if state.personality_traits is None:
            raise ValueError("personality_traits are required for this node.")

        if state.location is None:
            raise ValueError("location is required for this node.")

        if state.age is None:
            raise ValueError("age is required for this node.")

        if state.sex is None:
            raise ValueError("sex is required for this node.")

        # Create the request to gemini for avatar inspiration
        prompt = create_name_prompt(
            state.personality_traits, state.location.city, state.location.state, state.age, state.sex
        )
        logger.info(f"Creating response with prompt: {prompt}")

        grok_tool = GrokTool(prompt=prompt, model="grok-4-1-fast-non-reasoning")
        grok_result = await grok_tool.schema_request(CreateNameSchema)
        logger.info(f"Grok result: {grok_result}")

        # Update the state with the first name
        await store.set_first_name(grok_result.first_name)
        await store.set_last_name(grok_result.last_name)

        return
