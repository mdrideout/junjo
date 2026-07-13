from app.ai_services.gemini.gemini_tool import GeminiTool
from app.workflows.create_contact.nodes.create_bio.test.test_prompt import test_evaluate_bio_prompt
from app.workflows.create_contact.nodes.create_bio.test.test_schema import TestCreateBioSchema


async def eval_create_bio_node(bio: str) -> TestCreateBioSchema:
    """Perform the evaluation of the create_bio node."""

    # Create the request to gemini for avatar inspiration
    prompt = test_evaluate_bio_prompt(bio)

    gemini_tool = GeminiTool(prompt=prompt, model="gemini-3-flash-preview")
    gemini_result = await gemini_tool.schema_request(schema=TestCreateBioSchema)

    return gemini_result
