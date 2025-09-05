from junjo.node import Node
from loguru import logger

from app.ai_services.gemini.gemini_tool import GeminiTool
from app.workflows.create_contact.nodes.create_bio.prompt import create_bio_prompt
from app.workflows.create_contact.store import CreateContactStore


class CreateBioNode(Node[CreateContactStore]):
    """
    Node for creating the bio for a contact.
    """

    async def service(self, store: CreateContactStore) -> None:
        """
        Service method to create the bio for a contact.
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
        prompt = create_bio_prompt(
            state.personality_traits, state.location.city, state.location.state, state.age, state.sex
        )
        logger.info(f"Creating response with prompt: {prompt}")

        # Create a request to gemini
        gemini_tool = GeminiTool(prompt=prompt, model="gemini-2.5-flash")
        gemini_result = await gemini_tool.text_request()
        logger.info(f"Gemini result: {gemini_result}")

        # Update the state with the bio
        await store.set_bio(gemini_result)

        return
