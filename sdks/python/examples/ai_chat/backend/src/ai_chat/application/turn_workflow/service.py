"""Application facade for synchronous request/Workflow execution."""

from junjo import Agent

from ai_chat.application.dependencies import ChatDependencies
from ai_chat.domain.models import ChatAgentInput, ChatAgentOutput, TurnResult
from ai_chat.domain.ports import ContactReader, HistoryReader, IdFactory, ImageRenderer, MessageRepository

from .factory import create_turn_workflow


class ChatTurnService:
    def __init__(
        self,
        *,
        agent: Agent[ChatAgentInput, ChatAgentOutput, ChatDependencies],
        messages: MessageRepository,
        history: HistoryReader,
        contacts: ContactReader,
        images: ImageRenderer,
        id_factory: IdFactory,
    ) -> None:
        self._agent = agent
        self._messages = messages
        self._history = history
        self._contacts = contacts
        self._images = images
        self._id_factory = id_factory

    @property
    def agent(self) -> Agent[ChatAgentInput, ChatAgentOutput, ChatDependencies]:
        return self._agent

    async def submit(self, *, conversation_id: str, text: str) -> TurnResult:
        normalized_text = text.strip()
        if not normalized_text or len(normalized_text) > 2_500:
            raise ValueError("Turn text must contain between 1 and 2500 characters.")
        turn_id = self._id_factory()
        workflow = create_turn_workflow(
            conversation_id=conversation_id,
            turn_id=turn_id,
            text=normalized_text,
            agent=self._agent,
            messages=self._messages,
            history=self._history,
            contacts=self._contacts,
            images=self._images,
        )
        result = await workflow.execute()
        state = result.state
        if state.user_message is None or state.assistant_message is None or state.agent_run_id is None:
            raise RuntimeError("The completed turn Workflow is missing required output state.")
        return TurnResult(
            conversation_id=conversation_id,
            workflow_run_id=result.run_id,
            agent_run_id=state.agent_run_id,
            user_message=state.user_message,
            assistant_message=state.assistant_message,
        )
