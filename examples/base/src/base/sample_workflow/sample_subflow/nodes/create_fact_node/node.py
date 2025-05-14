from junjo import Node

from base.gemini_tool import GeminiTool
from base.sample_workflow.sample_subflow.nodes.create_fact_node.prompt import create_fact_prompt
from base.sample_workflow.sample_subflow.store import SampleSubflowStore


class CreateFactNode(Node[SampleSubflowStore]):
    """Workflow node that creates a fact based on the provided items."""

    async def service(self, store: SampleSubflowStore) -> None:
        # Get the current state
        state = await store.get_state()
        joke = state.joke

        # Null check for the required items
        if not joke:
            raise ValueError("No joke provided to create a fact.")

        # Create the request to gemini for avatar inspiration
        prompt = create_fact_prompt(joke)

        # Create a request to gemini
        gemini_tool = GeminiTool(prompt=prompt, model="gemini-2.0-flash-001")
        gemini_result = await gemini_tool.text_request()

        # Update the store with the new joke
        await store.set_fact(gemini_result)
        return
