from junjo.node import Node
from loguru import logger

from app.ai_services.grok import GrokTool
from app.workflows.test_sub_flow.store import TestSubFlowStore


class SubFlowNode2(Node[TestSubFlowStore]):
    """Test concurrent node."""

    async def service(self, store) -> None:
        # Construct the prompt
        prompt = 'Output a joke about a very large lasagna prepended by "SubFlowNode2:"'
        logger.info(f"Prompt: {prompt}")

        grok_tool = GrokTool(prompt=prompt, model="grok-4-1-fast-non-reasoning")
        grok_result = await grok_tool.text_request()
        logger.info(f"Grok result: {grok_result}")

        # Update state
        await store.append_joke(grok_result)

        return
