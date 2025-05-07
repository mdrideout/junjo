from loguru import logger

from app.ai_services.gemini.gemini_tool import GeminiTool
from app.workflows.create_contact.nodes.select_location.schemas import LocCityState
from app.workflows.create_contact.nodes.select_location.services.get_nearest_city_state_prompt import (
    get_nearest_city_state_prompt,
)


async def get_nearest_city_state(lat: float, long: float) -> LocCityState:
    """
    Get the nearest city and state using an LLM call.
    """

    # Construct the prompt
    prompt = get_nearest_city_state_prompt(lat, long)
    logger.info(f"Creating response with prompt: {prompt}")

    # Create a request to gemini
    gemini_tool = GeminiTool(prompt=prompt, model="gemini-2.0-flash-lite-001")
    gemini_result = await gemini_tool.schema_request(schema=LocCityState)
    logger.info(f"Gemini result: {gemini_result}")

    return gemini_result
