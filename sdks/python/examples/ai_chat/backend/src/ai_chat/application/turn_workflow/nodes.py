"""Single-responsibility Nodes in the model-powered handle-message Workflow."""

from junjo import Agent, Node
from pydantic import BaseModel

from ai_chat.application.dependencies import ChatDependencies
from ai_chat.domain.models import ChatAgentInput, ChatAgentOutput, MessageDirective
from ai_chat.domain.ports import ContactReader, HistoryReader, ImageModel, LanguageModel, TurnRepository

from .history import agent_history
from .prompts import directive_prompt, persona_response_prompt
from .state import TurnWorkflowStore


class DirectiveDecision(BaseModel):
    directive: MessageDirective


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
    """Load the persona required on every Turn."""

    def __init__(self, contacts: ContactReader) -> None:
        super().__init__()
        self._contacts = contacts

    async def service(self, store: TurnWorkflowStore) -> None:
        state = await store.get_state()
        contact = await self._contacts.get_contact_for_conversation(state.turn.conversation_id)
        await store.set_contact(contact)


class AssessMessageDirectiveNode(Node[TurnWorkflowStore]):
    """Use a typed model decision to select a known product procedure."""

    def __init__(self, language: LanguageModel) -> None:
        super().__init__()
        self._language = language

    async def service(self, store: TurnWorkflowStore) -> None:
        state = await store.get_state()
        decision = await self._language.generate_structured(
            prompt=directive_prompt(
                turns=state.recent_turns,
                current_message=state.turn.user_message.content,
            ),
            output_type=DirectiveDecision,
        )
        await store.set_directive(decision.directive)


class CreateWorkResponseNode(Node[TurnWorkflowStore]):
    def __init__(self, language: LanguageModel) -> None:
        super().__init__()
        self._language = language

    async def service(self, store: TurnWorkflowStore) -> None:
        state = await store.get_state()
        if state.contact is None:
            raise RuntimeError("Contact must be loaded before creating a work response.")
        message = await self._language.generate_text(
            prompt=persona_response_prompt(
                contact=state.contact,
                turns=state.recent_turns,
                current_message=state.turn.user_message.content,
                directive=(
                    "Continue or establish this person's specific work history. Build on earlier "
                    "details without merely repeating them. Invent coherent details only when none exist."
                ),
            )
        )
        await store.set_response(ChatAgentOutput(message=message))


class CreateDateIdeaResponseNode(Node[TurnWorkflowStore]):
    def __init__(self, language: LanguageModel) -> None:
        super().__init__()
        self._language = language

    async def service(self, store: TurnWorkflowStore) -> None:
        state = await store.get_state()
        if state.contact is None:
            raise RuntimeError("Contact must be loaded before creating a date response.")
        message = await self._language.generate_text(
            prompt=persona_response_prompt(
                contact=state.contact,
                turns=state.recent_turns,
                current_message=state.turn.user_message.content,
                directive=(
                    "Suggest specific real places in the contact's geographic area that this person "
                    "has visited or plausibly wants to visit. Respect prior preferences and be concrete."
                ),
            )
        )
        await store.set_response(ChatAgentOutput(message=message))


class CreateGeneralAgentResponseNode(Node[TurnWorkflowStore]):
    """Map mandatory Workflow context into one bounded Agent execution."""

    def __init__(
        self,
        *,
        agent: Agent[ChatAgentInput, ChatAgentOutput, ChatDependencies],
        history: HistoryReader,
        language: LanguageModel,
        images: ImageModel,
    ) -> None:
        super().__init__()
        self._agent = agent
        self._history = history
        self._language = language
        self._images = images

    async def service(self, store: TurnWorkflowStore) -> None:
        state = await store.get_state()
        if state.contact is None:
            raise RuntimeError("Contact must be loaded before executing the chat Agent.")
        dependencies = ChatDependencies(
            conversation_id=state.turn.conversation_id,
            turn_id=state.turn.id,
            before_sequence=state.turn.sequence,
            contact=state.contact,
            recent_turns=state.recent_turns,
            history=self._history,
            language=self._language,
            images=self._images,
        )
        result = await self._agent.execute(
            ChatAgentInput(
                conversation_id=state.turn.conversation_id,
                turn_id=state.turn.id,
                contact=state.contact,
                message=state.turn.user_message.content,
            ),
            dependencies=dependencies,
            history=agent_history(state.recent_turns, state.contact),
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
