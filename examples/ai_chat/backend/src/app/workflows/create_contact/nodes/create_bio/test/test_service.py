from app.ai_services.grok import GrokTool
from app.workflows.create_contact.nodes.create_bio.test.test_prompt import test_evaluate_bio_prompt
from app.workflows.create_contact.nodes.create_bio.test.test_schema import TestCreateBioSchema


async def eval_create_bio_node(bio: str) -> TestCreateBioSchema:
    """Perform the evaluation of the create_bio node."""

    # Create the request to gemini for avatar inspiration
    prompt = test_evaluate_bio_prompt(bio)

    grok_tool = GrokTool(prompt=prompt, model="grok-4-1-fast-non-reasoning")
    grok_result = await grok_tool.schema_request(schema=TestCreateBioSchema)

    return grok_result
