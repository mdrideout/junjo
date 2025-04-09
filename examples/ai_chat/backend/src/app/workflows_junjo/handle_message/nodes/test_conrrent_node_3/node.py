from junjo.node import Node
from loguru import logger
from nanoid import generate

from app.ai_services.gemini.gemini_tool import GeminiTool
from app.workflows_junjo.handle_message.store import MessageWorkflowStore


class TestConcurrentNode3(Node[MessageWorkflowStore]):
    """Test concurrent node."""

    async def service(self, store) -> None:
        # Concurrent instant set states to check for collision issues
        await store.set_concurrent_update_test_state(f"TestConcurrentNode3 - 1: {generate()}")
        await store.set_concurrent_update_test_state(f"TestConcurrentNode3 - 2: {generate()}")
        # await store.set_concurrent_update_test_state(f"TestConcurrentNode3 - 3: {generate()}")
        # await store.set_concurrent_update_test_state(f"TestConcurrentNode3 - 4: {generate()}")
        # await store.set_concurrent_update_test_state(f"TestConcurrentNode3 - 5: {generate()}")
        # await store.set_concurrent_update_test_state(f"TestConcurrentNode3 - 6: {generate()}")
        # await store.set_concurrent_update_test_state(f"TestConcurrentNode3 - 7: {generate()}")
        # await store.set_concurrent_update_test_state(f"TestConcurrentNode3 - 8: {generate()}")
        # await store.set_concurrent_update_test_state(f"TestConcurrentNode3 - 9: {generate()}")
        # await store.set_concurrent_update_test_state(f"TestConcurrentNode3 - 10: {generate()}")

        # Construct the prompt
        prompt = "Provide a word of the day and it's definition, prepended by \"TestConcurrentNode3:\""
        logger.info(f"Prompt: {prompt}")

        # Create a request to gemini
        gemini_tool = GeminiTool(prompt=prompt, model="gemini-1.5-flash-8b-001")
        gemini_result = await gemini_tool.text_request()
        logger.info(f"Gemini result: {gemini_result}")


        # Update state
        await store.append_test_update(gemini_result)

        return
