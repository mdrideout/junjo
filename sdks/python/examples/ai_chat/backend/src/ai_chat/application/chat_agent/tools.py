"""Typed Agent Tools with narrow application-owned responsibilities."""

from junjo import AgentRunContext, Tool

from ai_chat.application.dependencies import ChatDependencies
from ai_chat.application.image_workflow import create_image_workflow
from ai_chat.domain.models import (
    ContactProfileInput,
    ContactProfileOutput,
    CreateImageInput,
    CreateImageOutput,
    SearchHistoryInput,
    SearchHistoryOutput,
)


class SearchConversationHistoryService:
    async def __call__(
        self,
        input: SearchHistoryInput,
        context: AgentRunContext[ChatDependencies],
    ) -> SearchHistoryOutput:
        matches = await context.dependencies.history.search_history(
            context.dependencies.conversation_id,
            context.dependencies.before_sequence,
            input.query,
            input.limit,
        )
        return SearchHistoryOutput(matches=matches)


class GetContactProfileService:
    async def __call__(
        self,
        input: ContactProfileInput,
        context: AgentRunContext[ChatDependencies],
    ) -> ContactProfileOutput:
        contact = await context.dependencies.contacts.get_contact_for_conversation(context.dependencies.conversation_id)
        return ContactProfileOutput(
            display_name=contact.display_name,
            bio=contact.bio if input.include_bio else None,
        )


class CreateImageWorkflowService:
    async def __call__(
        self,
        input: CreateImageInput,
        context: AgentRunContext[ChatDependencies],
    ) -> CreateImageOutput:
        workflow = create_image_workflow(input, context.dependencies.images)
        result = await workflow.execute()
        if result.state.artifact is None:
            raise RuntimeError("The image Workflow completed without an artifact.")
        return CreateImageOutput(artifact=result.state.artifact)


def create_chat_tools() -> tuple[
    Tool[SearchHistoryInput, SearchHistoryOutput, ChatDependencies]
    | Tool[ContactProfileInput, ContactProfileOutput, ChatDependencies]
    | Tool[CreateImageInput, CreateImageOutput, ChatDependencies],
    ...,
]:
    """Construct immutable, stateless Tool definitions for the chat Agent."""

    history = Tool[SearchHistoryInput, SearchHistoryOutput, ChatDependencies](
        name="search_conversation_history",
        description="Search earlier completed messages in this conversation.",
        input_type=SearchHistoryInput,
        output_type=SearchHistoryOutput,
        shared_service=SearchConversationHistoryService(),
    )
    contact = Tool[ContactProfileInput, ContactProfileOutput, ChatDependencies](
        name="get_contact_profile",
        description="Read the profile associated with this conversation.",
        input_type=ContactProfileInput,
        output_type=ContactProfileOutput,
        shared_service=GetContactProfileService(),
    )
    image = Tool[CreateImageInput, CreateImageOutput, ChatDependencies](
        name="create_image",
        description="Run the structured image Workflow and return its artifact.",
        input_type=CreateImageInput,
        output_type=CreateImageOutput,
        shared_service=CreateImageWorkflowService(),
    )
    return (history, contact, image)
