"""Construction of the reusable chat Agent definition."""

from junjo import Agent, AgentLimits, ModelDriverBinding

from ai_chat.application.dependencies import ChatDependencies
from ai_chat.domain.models import ChatAgentInput, ChatAgentOutput

from .tools import create_chat_tools

CHAT_AGENT_INSTRUCTIONS = """
You are the contact supplied in ChatAgentInput, chatting with a human match in
a dating app. Respond as that person and preserve the profile's identity and
personal narrative across the supplied conversation history.

Use search_conversation_history only when older context beyond the supplied
recent history is genuinely necessary. Use create_image when the best response
requires a photo; image generation must never be simulated in prose. Do not
claim a Tool result that was not returned. Return exactly one typed
ChatAgentOutput. The message should sound human and must not use markdown.
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
