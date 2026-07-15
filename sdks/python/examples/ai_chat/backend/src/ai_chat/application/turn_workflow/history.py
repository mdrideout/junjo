"""Application-owned mapping from persisted turns into Agent history."""

from junjo.agent import AgentInputMessage, AgentMessage, AssistantOutputMessage

from ai_chat.domain.models import ChatAgentInput, ChatAgentOutput, CompletedTurn, ContactProfile


def agent_history(
    turns: tuple[CompletedTurn, ...],
    contact: ContactProfile,
) -> tuple[AgentMessage, ...]:
    """Map only complete persisted exchanges into the closed Agent grammar."""

    messages: list[AgentMessage] = []
    for turn in turns:
        messages.append(
            AgentInputMessage(
                ChatAgentInput(
                    conversation_id=turn.user.conversation_id,
                    turn_id=turn.user.turn_id,
                    contact=contact,
                    message=turn.user.content,
                ).model_dump(mode="json")
            )
        )
        messages.append(
            AssistantOutputMessage(
                ChatAgentOutput(
                    message=turn.assistant.content,
                    image=turn.assistant.image,
                ).model_dump(mode="json")
            )
        )
    return tuple(messages)
