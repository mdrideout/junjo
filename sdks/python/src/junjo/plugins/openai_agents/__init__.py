"""Optional OpenAI Agents SDK composition and telemetry integration."""

from ._instrumentation import (
    OpenAIAgentsIntegration,
    OpenAIAgentsIntegrationError,
    instrument_openai_agents,
)
from ._tools import (
    AgentToolInvocation,
    WorkflowToolInvocation,
    agent_as_tool,
    workflow_as_tool,
)

__all__ = [
    "AgentToolInvocation",
    "OpenAIAgentsIntegration",
    "OpenAIAgentsIntegrationError",
    "WorkflowToolInvocation",
    "agent_as_tool",
    "instrument_openai_agents",
    "workflow_as_tool",
]
