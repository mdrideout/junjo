from junjo.node import Node
from loguru import logger

from app.ai_services.grok import GrokTool
from app.workflows.sub_sub_flow.store import SubSubFlowStore


class SubSubFlowNode2(Node[SubSubFlowStore]):
    """Sub concurrent node."""

    async def service(self, store) -> None:
        # Construct the prompt
        prompt = "Output a fact about whales."
        logger.info(f"Prompt: {prompt}")

        grok_tool = GrokTool(prompt=prompt, model="grok-4-1-fast-non-reasoning")
        grok_result = await grok_tool.text_request()
        logger.info(f"Grok result: {grok_result}")

        # Update state
        await store.append_fact(grok_result)

        return
