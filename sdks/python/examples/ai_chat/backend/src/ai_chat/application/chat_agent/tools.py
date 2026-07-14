"""Typed Agent Tools with narrow application-owned responsibilities."""

from junjo import AgentRunContext, Tool

from ai_chat.application.dependencies import ChatDependencies
from ai_chat.application.image_workflow import create_image_workflow
from ai_chat.domain.models import (
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


class CreateImageWorkflowService:
    async def __call__(
        self,
        input: CreateImageInput,
        context: AgentRunContext[ChatDependencies],
    ) -> CreateImageOutput:
        workflow = create_image_workflow(
            input,
            contact=context.dependencies.contact,
            recent_turns=context.dependencies.recent_turns,
            language=context.dependencies.language,
            images=context.dependencies.images,
        )
        result = await workflow.execute()
        if result.state.output is None or result.state.output.image is None:
            raise RuntimeError("The image Workflow completed without an artifact.")
        return CreateImageOutput(artifact=result.state.output.image)


def create_chat_tools() -> tuple[
    Tool[SearchHistoryInput, SearchHistoryOutput, ChatDependencies]
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
    image = Tool[CreateImageInput, CreateImageOutput, ChatDependencies](
        name="create_image",
        description="Run the structured image Workflow and return its artifact.",
        input_type=CreateImageInput,
        output_type=CreateImageOutput,
        shared_service=CreateImageWorkflowService(),
    )
    return (history, image)
