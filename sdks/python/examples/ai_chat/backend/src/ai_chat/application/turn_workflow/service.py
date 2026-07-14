"""Application boundary for Turn admission and terminal reconciliation."""

from __future__ import annotations

import asyncio

from junjo import Agent, AgentError, ExecutionCorrelation

from ai_chat.application.dependencies import ChatDependencies
from ai_chat.domain.errors import TurnExecutionError
from ai_chat.domain.models import (
    ChatAgentInput,
    ChatAgentOutput,
    ContextPolicyReference,
    Turn,
    TurnFailure,
    TurnStatus,
)
from ai_chat.domain.ports import (
    ContactReader,
    HistoryReader,
    IdFactory,
    ImageRenderer,
    TurnRepository,
)

from .factory import create_turn_workflow


class ChatTurnService:
    """Admit one authoritative Turn and reconcile its outer execution."""

    def __init__(
        self,
        *,
        agent: Agent[ChatAgentInput, ChatAgentOutput, ChatDependencies],
        turns: TurnRepository,
        history: HistoryReader,
        contacts: ContactReader,
        images: ImageRenderer,
        id_factory: IdFactory,
    ) -> None:
        self._agent = agent
        self._turns = turns
        self._history = history
        self._contacts = contacts
        self._images = images
        self._id_factory = id_factory

    @property
    def agent(self) -> Agent[ChatAgentInput, ChatAgentOutput, ChatDependencies]:
        return self._agent

    async def admit(self, *, conversation_id: str, text: str) -> Turn:
        normalized_text = text.strip()
        if not normalized_text or len(normalized_text) > 2_500:
            raise ValueError("Turn text must contain between 1 and 2500 characters.")

        return await self._turns.admit_turn(
            conversation_id=conversation_id,
            turn_id=self._id_factory(),
            text=normalized_text,
            context_policy=ContextPolicyReference(),
        )

    async def execute(self, turn_id: str) -> Turn:
        turn = await self._turns.get_turn(turn_id)
        try:
            turn = await self._turns.start_turn(turn.id)
            workflow = create_turn_workflow(
                turn=turn,
                agent=self._agent,
                turns=self._turns,
                history=self._history,
                contacts=self._contacts,
                images=self._images,
            )
            result = await workflow.execute(correlation=ExecutionCorrelation(type="ai_chat.turn", id=turn.id))
            state = result.state
            if state.turn.assistant_message is None:
                raise RuntimeError("The completed Turn Workflow is missing its persisted response.")
            return await self._turns.complete_turn(
                turn_id=turn.id,
                workflow_run_id=result.run_id,
            )
        except asyncio.CancelledError as cancellation:
            await self._turns.terminate_turn(
                turn_id=turn.id,
                status=TurnStatus.CANCELLED,
                failure=TurnFailure(
                    code="turn_cancelled",
                    detail="Turn execution was cancelled.",
                    termination_reason="cancelled",
                ),
                agent_run_id=None,
            )
            raise cancellation
        except Exception as cause:
            agent_run_id = cause.run_id if isinstance(cause, AgentError) else None
            termination_reason = cause.termination_reason if isinstance(cause, AgentError) else None
            await self._turns.terminate_turn(
                turn_id=turn.id,
                status=TurnStatus.FAILED,
                failure=TurnFailure(
                    code=("agent_execution_failed" if isinstance(cause, AgentError) else "turn_execution_failed"),
                    detail=("Agent execution failed." if isinstance(cause, AgentError) else "Turn execution failed."),
                    termination_reason=termination_reason,
                ),
                agent_run_id=agent_run_id,
            )
            raise TurnExecutionError(turn.id) from cause

    async def submit(self, *, conversation_id: str, text: str) -> Turn:
        """Synchronous test and native-call convenience over admission/execution."""
        turn = await self.admit(conversation_id=conversation_id, text=text)
        return await self.execute(turn.id)
