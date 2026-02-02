from loguru import logger

from app.ai_services.grok import GrokTool
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

    grok_tool = GrokTool(prompt=prompt, model="grok-4-1-fast-non-reasoning")
    grok_result = await grok_tool.schema_request(schema=LocCityState)
    logger.info(f"Grok result: {grok_result}")

    return grok_result
