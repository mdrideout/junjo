"""Per-request deterministic turn Workflow factory."""

from junjo import Agent, Workflow

from ai_chat.application.dependencies import ChatDependencies
from ai_chat.domain.models import ChatAgentInput, ChatAgentOutput
from ai_chat.domain.ports import ContactReader, HistoryReader, ImageRenderer, MessageRepository

from .graph import create_turn_graph
from .state import TurnWorkflowState, TurnWorkflowStore


def create_turn_workflow(
    *,
    conversation_id: str,
    turn_id: str,
    text: str,
    agent: Agent[ChatAgentInput, ChatAgentOutput, ChatDependencies],
    messages: MessageRepository,
    history: HistoryReader,
    contacts: ContactReader,
    images: ImageRenderer,
) -> Workflow[TurnWorkflowState, TurnWorkflowStore]:
    return Workflow(
        name="Chat Turn Workflow",
        graph_factory=lambda: create_turn_graph(
            agent=agent,
            messages=messages,
            history=history,
            contacts=contacts,
            images=images,
        ),
        store_factory=lambda: TurnWorkflowStore(
            initial_state=TurnWorkflowState(
                conversation_id=conversation_id,
                turn_id=turn_id,
                text=text,
            )
        ),
        max_iterations=1,
    )
