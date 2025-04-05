from junjo.node import Node
from loguru import logger
from nanoid import generate

from app.ai_services.gemini.gemini_tool import GeminiTool
from app.workflows_junjo.handle_message.store import MessageWorkflowStore


class TestConcurrentNode1(Node[MessageWorkflowStore]):
    """Test concurrent node."""

    async def service(self, store) -> None:
        # Concurrent instant set states to check for collision issues
        await store.set_concurrent_update_test_state(self, f"TestConcurrentNode1 - 1: {generate()}")
        await store.set_concurrent_update_test_state(self, f"TestConcurrentNode1 - 2: {generate()}")
        # await store.set_concurrent_update_test_state(self, f"TestConcurrentNode1 - 3: {generate()}")
        # await store.set_concurrent_update_test_state(self, f"TestConcurrentNode1 - 4: {generate()}")
        # await store.set_concurrent_update_test_state(self, f"TestConcurrentNode1 - 5: {generate()}")
        # await store.set_concurrent_update_test_state(self, f"TestConcurrentNode1 - 6: {generate()}")
        # await store.set_concurrent_update_test_state(self, f"TestConcurrentNode1 - 7: {generate()}")
        # await store.set_concurrent_update_test_state(self, f"TestConcurrentNode1 - 8: {generate()}")
        # await store.set_concurrent_update_test_state(self, f"TestConcurrentNode1 - 9: {generate()}")
        # await store.set_concurrent_update_test_state(self, f"TestConcurrentNode1 - 10: {generate()}")

        # Construct the prompt
        prompt = "Output a joke about a horse prepended by \"TestConcurrentNode1:\""
        logger.info(f"Prompt: {prompt}")

        # Create a request to gemini
        gemini_tool = GeminiTool(prompt=prompt, model="gemini-1.5-flash-8b-001")
        gemini_result = await gemini_tool.text_request()
        logger.info(f"Gemini result: {gemini_result}")


        # Update state
        await store.append_test_update(self, gemini_result)

        return
