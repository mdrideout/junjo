"""Single-responsibility Nodes in the restored handle-message Workflow."""

from junjo import Agent, Node

from ai_chat.application.dependencies import ChatDependencies
from ai_chat.domain.models import (
    ChatAgentInput,
    ChatAgentOutput,
    MessageDirective,
)
from ai_chat.domain.ports import ContactReader, HistoryReader, ImageRenderer, TurnRepository

from .history import agent_history
from .state import TurnWorkflowStore


class LoadRecentContextNode(Node[TurnWorkflowStore]):
    """Load bounded history required on every Turn."""

    def __init__(self, history: HistoryReader) -> None:
        super().__init__()
        self._history = history

    async def service(self, store: TurnWorkflowStore) -> None:
        state = await store.get_state()
        recent_turns = await self._history.recent_completed_turns(
            state.turn.conversation_id,
            state.turn.sequence,
            state.turn.context_policy.recent_turn_limit,
        )
        await store.set_recent_turns(recent_turns)


class LoadContactNode(Node[TurnWorkflowStore]):
    """Load the conversation contact required on every Turn."""

    def __init__(self, contacts: ContactReader) -> None:
        super().__init__()
        self._contacts = contacts

    async def service(self, store: TurnWorkflowStore) -> None:
        state = await store.get_state()
        contact = await self._contacts.get_contact_for_conversation(state.turn.conversation_id)
        await store.set_contact(contact)


class AssessMessageDirectiveNode(Node[TurnWorkflowStore]):
    """Classify known product behaviors before bounded autonomous handling."""

    async def service(self, store: TurnWorkflowStore) -> None:
        state = await store.get_state()
        text = state.turn.user_message.content.casefold()
        if any(word in text for word in ("image", "picture", "draw", "illustrate")):
            directive = MessageDirective.IMAGE_RESPONSE
        elif any(word in text for word in ("date idea", "date night", "romantic")):
            directive = MessageDirective.DATE_IDEA_RESEARCH
        elif any(word in text for word in ("work", "job", "career", "office")):
            directive = MessageDirective.WORK_RELATED_RESPONSE
        else:
            directive = MessageDirective.GENERAL_RESPONSE
        await store.set_directive(directive)


class CreateWorkResponseNode(Node[TurnWorkflowStore]):
    async def service(self, store: TurnWorkflowStore) -> None:
        state = await store.get_state()
        if state.contact is None:
            raise RuntimeError("Contact must be loaded before creating a work response.")
        await store.set_response(
            ChatAgentOutput(
                message=(
                    f"{state.contact.first_name} thinks a good first step is to make "
                    "the work problem smaller, write down the next concrete action, "
                    "and protect a short block of focus time for it."
                )
            )
        )


class CreateDateIdeaResponseNode(Node[TurnWorkflowStore]):
    async def service(self, store: TurnWorkflowStore) -> None:
        state = await store.get_state()
        if state.contact is None:
            raise RuntimeError("Contact must be loaded before creating a date response.")
        await store.set_response(
            ChatAgentOutput(
                message=(
                    f"For a date with {state.contact.first_name}, try a relaxed walk "
                    f"somewhere interesting in {state.contact.city}, then pick a small "
                    "restaurant neither of you has tried."
                )
            )
        )


class CreateGeneralAgentResponseNode(Node[TurnWorkflowStore]):
    """Map Workflow state into one bounded Agent execution."""

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
        dependencies = ChatDependencies(
            conversation_id=state.turn.conversation_id,
            turn_id=state.turn.id,
            before_sequence=state.turn.sequence,
            history=self._history,
            contacts=self._contacts,
            images=self._images,
        )
        result = await self._agent.execute(
            ChatAgentInput(
                conversation_id=state.turn.conversation_id,
                turn_id=state.turn.id,
                message=state.turn.user_message.content,
            ),
            dependencies=dependencies,
            history=agent_history(state.recent_turns),
        )
        await store.set_response(result.output, agent_run_id=result.run_id)


class PersistOutcomeNode(Node[TurnWorkflowStore]):
    """Persist the selected branch response as application data."""

    def __init__(self, turns: TurnRepository) -> None:
        super().__init__()
        self._turns = turns

    async def service(self, store: TurnWorkflowStore) -> None:
        state = await store.get_state()
        if state.response is None:
            raise RuntimeError("A response is required before persistence.")
        turn = await self._turns.record_turn_outcome(
            turn_id=state.turn.id,
            output=state.response,
            agent_run_id=state.agent_run_id,
        )
        await store.set_persisted_turn(turn)
