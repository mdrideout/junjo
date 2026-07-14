"""Three explicit ownership steps in the chat turn Workflow."""

from junjo import Agent, Node

from ai_chat.application.dependencies import ChatDependencies
from ai_chat.domain.models import ChatAgentInput, ChatAgentOutput
from ai_chat.domain.ports import ContactReader, HistoryReader, ImageRenderer, MessageRepository

from .history import agent_history
from .state import TurnWorkflowStore


class PersistInputNode(Node[TurnWorkflowStore]):
    """Persist the user's input before autonomous processing begins."""

    def __init__(self, messages: MessageRepository) -> None:
        super().__init__()
        self._messages = messages

    async def service(self, store: TurnWorkflowStore) -> None:
        state = await store.get_state()
        message = await self._messages.append_user_message(
            conversation_id=state.conversation_id,
            turn_id=state.turn_id,
            content=state.text,
        )
        await store.set_user_message(message)


class ExecuteAgentNode(Node[TurnWorkflowStore]):
    """Map detached Workflow state into one isolated Agent execution."""

    def __init__(
        self,
        *,
        agent: Agent[ChatAgentInput, ChatAgentOutput, ChatDependencies],
        history: HistoryReader,
        contacts: ContactReader,
        images: ImageRenderer,
    ) -> None:
        super().__init__()
        self._agent = agent
        self._history = history
        self._contacts = contacts
        self._images = images

    async def service(self, store: TurnWorkflowStore) -> None:
        state = await store.get_state()
        if state.user_message is None:
            raise RuntimeError("The user message must be persisted before Agent execution.")
        prior_turns = await self._history.completed_turns_before(
            state.conversation_id,
            state.turn_id,
        )
        dependencies = ChatDependencies(
            conversation_id=state.conversation_id,
            turn_id=state.turn_id,
            history=self._history,
            contacts=self._contacts,
            images=self._images,
        )
        result = await self._agent.execute(
            ChatAgentInput(
                conversation_id=state.conversation_id,
                turn_id=state.turn_id,
                message=state.text,
            ),
            dependencies=dependencies,
            history=agent_history(prior_turns),
        )
        await store.set_agent_result(output=result.output, run_id=result.run_id)


class PersistResultNode(Node[TurnWorkflowStore]):
    """Persist the validated detached Agent output as application data."""

    def __init__(self, messages: MessageRepository) -> None:
        super().__init__()
        self._messages = messages

    async def service(self, store: TurnWorkflowStore) -> None:
        state = await store.get_state()
        if state.agent_output is None:
            raise RuntimeError("A validated Agent output is required before persistence.")
        message = await self._messages.append_assistant_message(
            conversation_id=state.conversation_id,
            turn_id=state.turn_id,
            output=state.agent_output,
        )
        await store.set_assistant_message(message)
