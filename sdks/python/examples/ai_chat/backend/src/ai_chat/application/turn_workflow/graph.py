"""Restored handle-message Graph with explicit deterministic boundaries."""

from junjo import Agent, Edge, Graph, RunConcurrent

from ai_chat.application.dependencies import ChatDependencies
from ai_chat.application.image_workflow.graph import create_image_graph
from ai_chat.application.image_workflow.state import ImageWorkflowState, ImageWorkflowStore
from ai_chat.domain.models import ChatAgentInput, ChatAgentOutput, MessageDirective
from ai_chat.domain.ports import ContactReader, HistoryReader, ImageRenderer, TurnRepository

from .conditions import DirectiveIs
from .image_subflow import ImageResponseSubflow
from .nodes import (
    AssessMessageDirectiveNode,
    CreateDateIdeaResponseNode,
    CreateGeneralAgentResponseNode,
    CreateWorkResponseNode,
    LoadContactNode,
    LoadRecentContextNode,
    PersistOutcomeNode,
)


def create_turn_graph(
    *,
    agent: Agent[ChatAgentInput, ChatAgentOutput, ChatDependencies],
    turns: TurnRepository,
    history: HistoryReader,
    contacts: ContactReader,
    images: ImageRenderer,
) -> Graph:
    initial_data = RunConcurrent(
        name="Load Turn Context",
        items=[LoadRecentContextNode(history), LoadContactNode(contacts)],
    )
    assess = AssessMessageDirectiveNode()
    work_response = CreateWorkResponseNode()
    date_response = CreateDateIdeaResponseNode()
    image_response = ImageResponseSubflow(
        name="Create Image Response Subflow",
        graph_factory=lambda: create_image_graph(images),
        store_factory=lambda: ImageWorkflowStore(initial_state=ImageWorkflowState(prompt="")),
        max_iterations=1,
    )
    general_response = CreateGeneralAgentResponseNode(
        agent=agent,
        history=history,
        contacts=contacts,
        images=images,
    )
    persist = PersistOutcomeNode(turns)
    return Graph(
        source=initial_data,
        sinks=[persist],
        edges=[
            Edge(tail=initial_data, head=assess),
            Edge(
                tail=assess,
                head=work_response,
                condition=DirectiveIs(MessageDirective.WORK_RELATED_RESPONSE),
            ),
            Edge(
                tail=assess,
                head=date_response,
                condition=DirectiveIs(MessageDirective.DATE_IDEA_RESEARCH),
            ),
            Edge(
                tail=assess,
                head=image_response,
                condition=DirectiveIs(MessageDirective.IMAGE_RESPONSE),
            ),
            Edge(tail=assess, head=general_response),
            Edge(tail=work_response, head=persist),
            Edge(tail=date_response, head=persist),
            Edge(tail=image_response, head=persist),
            Edge(tail=general_response, head=persist),
        ],
    )
