from junjo.node import Node
from loguru import logger

from app.ai_services.gemini.gemini_tool import GeminiTool
from app.workflows.sub_sub_flow.store import SubSubFlowStore


class SubSubFlowNode2(Node[SubSubFlowStore]):
    """Sub concurrent node."""

    async def service(self, store) -> None:
        # Construct the prompt
        prompt = "Output a fact about whales."
        logger.info(f"Prompt: {prompt}")

        # Create a request to gemini
        gemini_tool = GeminiTool(prompt=prompt, model="gemini-1.5-flash-8b-001")
        gemini_result = await gemini_tool.text_request()
        logger.info(f"Gemini result: {gemini_result}")


        # Update state
        await store.append_fact(gemini_result)

        return
