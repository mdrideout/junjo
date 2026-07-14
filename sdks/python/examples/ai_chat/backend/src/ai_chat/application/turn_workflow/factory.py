"""Per-request deterministic turn Workflow factory."""

from junjo import Agent, Workflow

from ai_chat.application.dependencies import ChatDependencies
from ai_chat.domain.models import ChatAgentInput, ChatAgentOutput, Turn
from ai_chat.domain.ports import (
    ContactReader,
    HistoryReader,
    ImageModel,
    LanguageModel,
    TurnRepository,
)

from .graph import create_turn_graph
from .state import TurnWorkflowState, TurnWorkflowStore


def create_turn_workflow(
    *,
    turn: Turn,
    agent: Agent[ChatAgentInput, ChatAgentOutput, ChatDependencies],
    turns: TurnRepository,
    history: HistoryReader,
    contacts: ContactReader,
    language: LanguageModel,
    images: ImageModel,
) -> Workflow[TurnWorkflowState, TurnWorkflowStore]:
    return Workflow(
        name="Chat Turn Workflow",
        graph_factory=lambda: create_turn_graph(
            agent=agent,
            turns=turns,
            history=history,
            contacts=contacts,
            language=language,
            images=images,
        ),
        store_factory=lambda: TurnWorkflowStore(initial_state=TurnWorkflowState(turn=turn)),
        max_iterations=1,
    )
