
from base.gemini_tool import GeminiTool
from base.sample_workflow.sample_subflow.nodes.create_joke_node.test.test_prompt import test_evaluate_joke_prompt
from base.sample_workflow.sample_subflow.nodes.create_joke_node.test.test_schema import TestCreateJokeSchema


async def eval_create_joke_node(joke: str, items: list[str]) -> TestCreateJokeSchema:
    """Perform the evaluation of the create_joke node."""

    # Create the request to gemini for avatar inspiration
    prompt = test_evaluate_joke_prompt(joke, items)

    # Create a request to gemini
    gemini_tool = GeminiTool(prompt=prompt, model="gemini-2.0-flash-001")
    gemini_result = await gemini_tool.schema_request(schema=TestCreateJokeSchema)

    return gemini_result
