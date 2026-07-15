"""Typed failures that retain admitted Workflow execution identity."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from types import MappingProxyType
from typing import Generic, TypeVar

from ._json import require_ijson_text
from .state import BaseState

StateT = TypeVar("StateT", bound=BaseState)


class WorkflowExecutionError(Exception, Generic[StateT]):
    """Failure raised after a Workflow or Subflow execution was admitted.

    The original execution failure is retained as ``__cause__``. The error
    itself owns the trustworthy Junjo execution identity and a detached final
    Store snapshot, so application code does not need Hooks or telemetry
    queries merely to persist the failed run's identity.

    :param message: Safe summary of the failed execution boundary.
    :type message: str
    :param run_id: Unique runtime identity of the admitted execution.
    :type run_id: str
    :param definition_id: Stable in-process Workflow definition identity.
    :type definition_id: str
    :param name: Configured Workflow or Subflow name.
    :type name: str
    :param state: Detached final state snapshot collected during terminalization.
    :type state: StateT
    :param state_is_terminal: Whether terminal Store evidence collection
        completed. When ``False``, ``state`` is the last detached snapshot
        available during emergency recovery.
    :type state_is_terminal: bool
    :param terminalization_error: A separate failure encountered while
        collecting terminal Store evidence, if any. The selected execution
        failure remains ``__cause__``.
    :type terminalization_error: BaseException | None
    :param node_execution_counts: Current-scope execution counts observed before
        failure.
    :type node_execution_counts: Mapping[str, int]
    """

    def __init__(
        self,
        message: str,
        *,
        run_id: str,
        definition_id: str,
        name: str,
        state: StateT,
        node_execution_counts: Mapping[str, int],
        state_is_terminal: bool = True,
        terminalization_error: BaseException | None = None,
    ) -> None:
        super().__init__(require_ijson_text(message, "Workflow error message", nonempty=True))
        _validate_terminal_snapshot_claim(state_is_terminal, terminalization_error)
        self.run_id = require_ijson_text(run_id, "run_id", nonempty=True)
        self.definition_id = require_ijson_text(
            definition_id,
            "definition_id",
            nonempty=True,
        )
        self.name = require_ijson_text(name, "Workflow name", nonempty=True)
        self.state = state
        self.node_execution_counts = MappingProxyType(dict(node_execution_counts))
        self.state_is_terminal = state_is_terminal
        self.terminalization_error = terminalization_error


class WorkflowCancelledError(asyncio.CancelledError, Generic[StateT]):
    """Caller-visible Workflow cancellation with admitted execution identity.

    This remains an :class:`asyncio.CancelledError`, so normal task
    cancellation handling continues to work. Its ``args`` preserve the
    original cancellation reason and the original cancellation is retained as
    ``__cause__``. The additional fields identify the admitted execution and
    expose its detached terminal state.

    :param run_id: Unique runtime identity of the admitted execution.
    :type run_id: str
    :param definition_id: Stable in-process Workflow definition identity.
    :type definition_id: str
    :param name: Configured Workflow or Subflow name.
    :type name: str
    :param state: Detached final state snapshot collected during terminalization.
    :type state: StateT
    :param state_is_terminal: Whether terminal Store evidence collection
        completed. When ``False``, ``state`` is the last detached snapshot
        available during emergency recovery.
    :type state_is_terminal: bool
    :param terminalization_error: A separate failure encountered while
        collecting terminal Store evidence, if any. The original cancellation
        remains ``__cause__``.
    :type terminalization_error: BaseException | None
    :param node_execution_counts: Current-scope execution counts observed before
        cancellation.
    :type node_execution_counts: Mapping[str, int]
    """

    def __init__(
        self,
        *cancel_args: object,
        run_id: str,
        definition_id: str,
        name: str,
        state: StateT,
        node_execution_counts: Mapping[str, int],
        state_is_terminal: bool = True,
        terminalization_error: BaseException | None = None,
    ) -> None:
        super().__init__(*cancel_args)
        _validate_terminal_snapshot_claim(state_is_terminal, terminalization_error)
        self.run_id = require_ijson_text(run_id, "run_id", nonempty=True)
        self.definition_id = require_ijson_text(
            definition_id,
            "definition_id",
            nonempty=True,
        )
        self.name = require_ijson_text(name, "Workflow name", nonempty=True)
        self.state = state
        self.node_execution_counts = MappingProxyType(dict(node_execution_counts))
        self.state_is_terminal = state_is_terminal
        self.terminalization_error = terminalization_error


def _validate_terminal_snapshot_claim(
    state_is_terminal: bool,
    terminalization_error: BaseException | None,
) -> None:
    if not isinstance(state_is_terminal, bool):
        raise TypeError("state_is_terminal must be a bool.")
    if terminalization_error is not None and not isinstance(
        terminalization_error,
        BaseException,
    ):
        raise TypeError("terminalization_error must be a BaseException or None.")
    if state_is_terminal != (terminalization_error is None):
        raise ValueError("state_is_terminal must be false exactly when terminalization_error is present.")
