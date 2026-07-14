"""State and explicit actions for the deterministic turn shell."""

from junjo import BaseState, BaseStore

from ai_chat.domain.models import ChatAgentOutput, ChatMessage


class TurnWorkflowState(BaseState):
    conversation_id: str
    turn_id: str
    text: str
    user_message: ChatMessage | None = None
    agent_output: ChatAgentOutput | None = None
    agent_run_id: str | None = None
    assistant_message: ChatMessage | None = None


class TurnWorkflowStore(BaseStore[TurnWorkflowState]):
    async def set_user_message(self, message: ChatMessage) -> None:
        await self.set_state({"user_message": message})

    async def set_agent_result(self, *, output: ChatAgentOutput, run_id: str) -> None:
        await self.set_state({"agent_output": output, "agent_run_id": run_id})

    async def set_assistant_message(self, message: ChatMessage) -> None:
        await self.set_state({"assistant_message": message})
