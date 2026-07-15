"""Application boundary for Turn admission and terminal reconciliation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable

from junjo import (
    Agent,
    AgentError,
    ExecutionCorrelation,
    WorkflowCancelledError,
    WorkflowExecutionError,
)

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
    ImageModel,
    LanguageModel,
    TurnRepository,
)

from .factory import create_turn_workflow
from .state import TurnWorkflowState


class ChatTurnService:
    """Admit one authoritative Turn and reconcile its outer execution."""

    def __init__(
        self,
        *,
        agent: Agent[ChatAgentInput, ChatAgentOutput, ChatDependencies],
        turns: TurnRepository,
        history: HistoryReader,
        contacts: ContactReader,
        language: LanguageModel,
        images: ImageModel,
        id_factory: IdFactory,
    ) -> None:
        self._agent = agent
        self._turns = turns
        self._history = history
        self._contacts = contacts
        self._language = language
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
        workflow_run_id: str | None = None
        agent_run_id: str | None = None
        try:
            turn = await self._turns.start_turn(turn.id)
            workflow = create_turn_workflow(
                turn=turn,
                agent=self._agent,
                turns=self._turns,
                history=self._history,
                contacts=self._contacts,
                language=self._language,
                images=self._images,
            )
            result = await workflow.execute(correlation=ExecutionCorrelation(type="ai_chat.turn", id=turn.id))
            workflow_run_id = result.run_id
            state = result.state
            agent_run_id = state.agent_run_id
            if state.turn.assistant_message is None:
                raise RuntimeError("The completed Turn Workflow is missing its persisted response.")
            completed_turn, completion_cancellation = await _drain_terminal_write(
                self._turns.complete_turn(
                    turn_id=turn.id,
                    workflow_run_id=result.run_id,
                )
            )
        except asyncio.CancelledError as cancellation:
            workflow_run_id = _workflow_run_id(cancellation) or workflow_run_id
            agent_run_id = _workflow_state_agent_run_id(cancellation) or agent_run_id
            await _drain_terminal_write(
                self._turns.terminate_turn(
                    turn_id=turn.id,
                    status=TurnStatus.CANCELLED,
                    failure=TurnFailure(
                        code="turn_cancelled",
                        detail="Turn execution was cancelled.",
                        termination_reason="cancelled",
                    ),
                    workflow_run_id=workflow_run_id,
                    agent_run_id=agent_run_id,
                )
            )
            raise cancellation
        except Exception as cause:
            workflow_run_id = _workflow_run_id(cause) or workflow_run_id
            agent_error = _find_agent_error(cause)
            agent_run_id = (
                agent_error.run_id if agent_error is not None else _workflow_state_agent_run_id(cause) or agent_run_id
            )
            termination_reason = agent_error.termination_reason if agent_error is not None else None
            _, terminal_write_cancellation = await _drain_terminal_write(
                self._turns.terminate_turn(
                    turn_id=turn.id,
                    status=TurnStatus.FAILED,
                    failure=TurnFailure(
                        code=("agent_execution_failed" if agent_error is not None else "turn_execution_failed"),
                        detail=("Agent execution failed." if agent_error is not None else "Turn execution failed."),
                        termination_reason=termination_reason,
                    ),
                    workflow_run_id=workflow_run_id,
                    agent_run_id=agent_run_id,
                )
            )
            if terminal_write_cancellation is not None:
                raise terminal_write_cancellation from cause
            raise TurnExecutionError(turn.id) from cause

        if completion_cancellation is not None:
            raise completion_cancellation
        return completed_turn

    async def submit(self, *, conversation_id: str, text: str) -> Turn:
        """Synchronous test and native-call convenience over admission/execution."""
        turn = await self.admit(conversation_id=conversation_id, text=text)
        return await self.execute(turn.id)


def _find_agent_error(error: BaseException) -> AgentError | None:
    """Return the first typed Agent boundary in one explicit cause chain."""

    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        if isinstance(current, AgentError):
            return current
        visited.add(id(current))
        current = current.__cause__
    return None


def _workflow_run_id(error: BaseException) -> str | None:
    if isinstance(error, WorkflowExecutionError | WorkflowCancelledError):
        return error.run_id
    return None


def _workflow_state_agent_run_id(error: BaseException) -> str | None:
    if isinstance(error, WorkflowExecutionError | WorkflowCancelledError):
        state = error.state
        if isinstance(state, TurnWorkflowState):
            return state.agent_run_id
    return None


async def _drain_terminal_write(
    write: Awaitable[Turn],
) -> tuple[Turn, asyncio.CancelledError | None]:
    """Finish one selected Turn transition before propagating cancellation."""

    task = asyncio.ensure_future(write)
    remembered_cancellation: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as cancellation:
            if remembered_cancellation is None:
                remembered_cancellation = cancellation
    return task.result(), remembered_cancellation
