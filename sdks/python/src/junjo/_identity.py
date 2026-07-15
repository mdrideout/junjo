"""Truthful executable identity shared by lifecycle domains."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum


class ExecutableType(StrEnum):
    """Junjo executable kind, independent from its telemetry encoding."""

    WORKFLOW = "workflow"
    SUBFLOW = "subflow"
    NODE = "node"
    RUN_CONCURRENT = "run_concurrent"
    AGENT = "agent"


@dataclass(frozen=True, slots=True)
class ParentExecutableIdentity:
    """Non-recursive semantic identity of a containing executable."""

    executable_definition_id: str
    executable_runtime_id: str
    executable_structural_id: str
    executable_type: ExecutableType


@dataclass(frozen=True, slots=True)
class ActiveExecutableIdentity:
    """Immutable identity of the executable active in the current task context."""

    executable_definition_id: str
    executable_name: str
    executable_type: ExecutableType
    executable_runtime_id: str
    executable_structural_id: str

    def as_parent(self) -> ParentExecutableIdentity:
        return ParentExecutableIdentity(
            executable_definition_id=self.executable_definition_id,
            executable_runtime_id=self.executable_runtime_id,
            executable_structural_id=self.executable_structural_id,
            executable_type=self.executable_type,
        )


_ACTIVE_EXECUTABLE_STACK: ContextVar[tuple[ActiveExecutableIdentity, ...]] = ContextVar(
    "junjo_active_executable_stack",
    default=(),
)


@contextmanager
def active_executable_identity(identity: ActiveExecutableIdentity):
    stack = _ACTIVE_EXECUTABLE_STACK.get()
    token = _ACTIVE_EXECUTABLE_STACK.set((*stack, identity))
    try:
        yield
    finally:
        _ACTIVE_EXECUTABLE_STACK.reset(token)


def get_active_executable_identity() -> ActiveExecutableIdentity | None:
    stack = _ACTIVE_EXECUTABLE_STACK.get()
    return stack[-1] if stack else None


def get_parent_active_executable_identity() -> ActiveExecutableIdentity | None:
    stack = _ACTIVE_EXECUTABLE_STACK.get()
    return stack[-2] if len(stack) >= 2 else None
