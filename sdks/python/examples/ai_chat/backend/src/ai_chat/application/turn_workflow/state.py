"""State and explicit actions for the deterministic turn shell."""

from junjo import BaseState, BaseStore

from ai_chat.domain.models import (
    ChatAgentOutput,
    CompletedTurn,
    ContactProfile,
    MessageDirective,
    Turn,
)


class TurnWorkflowState(BaseState):
    turn: Turn
    recent_turns: tuple[CompletedTurn, ...] = ()
    contact: ContactProfile | None = None
    directive: MessageDirective | None = None
    response: ChatAgentOutput | None = None
    agent_run_id: str | None = None


class TurnWorkflowStore(BaseStore[TurnWorkflowState]):
    async def set_recent_turns(self, turns: tuple[CompletedTurn, ...]) -> None:
        await self.set_state({"recent_turns": turns})

    async def set_contact(self, contact: ContactProfile) -> None:
        await self.set_state({"contact": contact})

    async def set_directive(self, directive: MessageDirective) -> None:
        await self.set_state({"directive": directive})

    async def set_response(
        self,
        response: ChatAgentOutput,
        *,
        agent_run_id: str | None = None,
    ) -> None:
        await self.set_state({"response": response, "agent_run_id": agent_run_id})

    async def set_persisted_turn(self, turn: Turn) -> None:
        await self.set_state({"turn": turn})
