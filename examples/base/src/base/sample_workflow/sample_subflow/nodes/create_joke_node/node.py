from junjo import Node

from base.gemini_tool import GeminiTool
from base.sample_workflow.sample_subflow.nodes.create_joke_node.prompt import create_joke_prompt
from base.sample_workflow.sample_subflow.store import SampleSubflowStore


class CreateJokeNode(Node[SampleSubflowStore]):
    """Workflow node that creates a joke based on the provided items."""

    async def service(self, store: SampleSubflowStore) -> None:
        # Get the current state
        state = await store.get_state()
        items = state.items

        # Null check for the required items
        if not items:
            raise ValueError("No items provided to create a joke.")

        # Create the request to gemini for avatar inspiration
        prompt = create_joke_prompt(items)

        # Create a request to gemini
        gemini_tool = GeminiTool(prompt=prompt, model="gemini-2.0-flash-001")
        gemini_result = await gemini_tool.text_request()

        # Update the store with the new joke
        await store.set_joke(gemini_result)
        return
