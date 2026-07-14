"""Construction of the reusable chat Agent definition."""

from junjo import Agent, AgentLimits, ModelDriverBinding

from ai_chat.application.dependencies import ChatDependencies
from ai_chat.domain.models import ChatAgentInput, ChatAgentOutput

from .tools import create_chat_tools

CHAT_AGENT_INSTRUCTIONS = """
Respond to the user's current message. Use a declared Tool only when its
capability is needed. Conversation and contact Tools are read-only. Image
creation must use create_image. Return exactly one typed ChatAgentOutput.
""".strip()


def create_chat_agent(
    model: ModelDriverBinding,
    *,
    limits: AgentLimits | None = None,
) -> Agent[ChatAgentInput, ChatAgentOutput, ChatDependencies]:
    return Agent(
        key="ai_chat",
        name="AI Chat Agent",
        instructions=CHAT_AGENT_INSTRUCTIONS,
        input_type=ChatAgentInput,
        model=model,
        tools=create_chat_tools(),
        output_type=ChatAgentOutput,
        limits=limits or AgentLimits(model_requests=4, tool_calls=4),
    )
