from junjo.node import Node
from loguru import logger

from app.ai_services.gemini.gemini_tool import GeminiTool
from app.workflows.test_sub_flow.store import TestSubFlowStore


class SubFlowNode2(Node[TestSubFlowStore]):
    """Test concurrent node."""

    async def service(self, store) -> None:
        # Construct the prompt
        prompt = 'Output a joke about a very large lasagna prepended by "SubFlowNode2:"'
        logger.info(f"Prompt: {prompt}")

        gemini_tool = GeminiTool(prompt=prompt, model="gemini-3-flash-preview")
        gemini_result = await gemini_tool.text_request()
        logger.info(f"Gemini result: {gemini_result}")

        # Update state
        await store.append_joke(gemini_result)

        return
