"""Fresh outer turn Graph construction."""

from junjo import Agent, Edge, Graph

from ai_chat.application.dependencies import ChatDependencies
from ai_chat.domain.models import ChatAgentInput, ChatAgentOutput
from ai_chat.domain.ports import ContactReader, HistoryReader, ImageRenderer, MessageRepository

from .nodes import ExecuteAgentNode, PersistInputNode, PersistResultNode


def create_turn_graph(
    *,
    agent: Agent[ChatAgentInput, ChatAgentOutput, ChatDependencies],
    messages: MessageRepository,
    history: HistoryReader,
    contacts: ContactReader,
    images: ImageRenderer,
) -> Graph:
    persist_input = PersistInputNode(messages)
    execute_agent = ExecuteAgentNode(
        agent=agent,
        history=history,
        contacts=contacts,
        images=images,
    )
    persist_result = PersistResultNode(messages)
    return Graph(
        source=persist_input,
        sinks=[persist_result],
        edges=[
            Edge(tail=persist_input, head=execute_agent),
            Edge(tail=execute_agent, head=persist_result),
        ],
    )
