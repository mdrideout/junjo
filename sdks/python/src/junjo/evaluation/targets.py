"""Typed Node, Workflow, and Agent evaluation target declarations."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Generic, TypeVar, cast

from pydantic import TypeAdapter, ValidationError
from typing_extensions import TypeForm

from ..agent import Agent, AgentError, AgentExecutionError
from ..agent.messages import AgentMessage
from ..agent.result import AgentExecutionResult
from ..correlation import ExecutionCorrelation
from ..eval import NodeEvaluationResult, evaluate_node
from ..node import Node
from ..state import BaseState
from ..store import BaseStore
from ..studio import ExecutableType, SemanticExecutionReference, TargetKind
from ..workflow import ExecutionResult, Workflow
from ..workflow_errors import WorkflowExecutionError
from .context import EvaluationContext

InputT = TypeVar("InputT")
StateT = TypeVar("StateT", bound=BaseState)
AgentInputT = TypeVar("AgentInputT")
AgentOutputT = TypeVar("AgentOutputT")
DependenciesT = TypeVar("DependenciesT")
CallbackResultT = TypeVar("CallbackResultT")
ResourcesT = TypeVar("ResourcesT")
Cleanup = Callable[[], None | Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ExecutionServiceIdentity:
    """Application OpenTelemetry service identity used for Studio resolution."""

    service_namespace: str
    service_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.service_namespace, str) or len(self.service_namespace) > 256:
            raise ValueError("service_namespace must be a string of at most 256 characters.")
        if not isinstance(self.service_name, str) or not self.service_name.strip() or len(self.service_name) > 256:
            raise ValueError("service_name must be a non-empty string of at most 256 characters.")

    def reference(
        self,
        *,
        executable_type: ExecutableType,
        runtime_id: str,
    ) -> SemanticExecutionReference:
        """Create the exact semantic identity accepted by Studio."""

        return SemanticExecutionReference(
            service_namespace=self.service_namespace,
            service_name=self.service_name,
            executable_type=executable_type,
            runtime_id=runtime_id,
        )


@dataclass(frozen=True, slots=True)
class TargetExecution:
    """Successful projected subject plus truthful top-level execution identity."""

    subject: object
    execution: SemanticExecutionReference
    duration_ms: int

    def __post_init__(self) -> None:
        if not 0 <= self.duration_ms <= 86_400_000:
            raise ValueError("Target duration_ms must be between 0 and 86400000.")


class TargetContractError(ValueError):
    """A target key, version, declaration, or typed input is invalid."""


class TargetExecutionError(RuntimeError):
    """A target failed, retaining execution identity whenever one exists."""

    def __init__(
        self,
        message: str,
        *,
        execution: SemanticExecutionReference | None,
        duration_ms: int,
    ) -> None:
        super().__init__(message[:1_000])
        self.execution = execution
        self.duration_ms = duration_ms


@dataclass(frozen=True, slots=True)
class NodeInvocation(Generic[StateT]):
    """Fresh Node and initialized Store constructed for one case."""

    node: Node
    store: BaseStore[StateT]
    correlation: ExecutionCorrelation | None = None
    cleanup: Cleanup | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.node, Node):
            raise TypeError("NodeInvocation node must be a Node.")
        if not isinstance(self.store, BaseStore):
            raise TypeError("NodeInvocation store must be a BaseStore.")
        _validate_correlation(self.correlation)
        _validate_cleanup(self.cleanup)


@dataclass(frozen=True, slots=True)
class WorkflowInvocation:
    """Fresh Workflow definition constructed for one case."""

    workflow: Workflow
    correlation: ExecutionCorrelation | None = None
    cleanup: Cleanup | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.workflow, Workflow):
            raise TypeError("WorkflowInvocation workflow must be a Workflow.")
        _validate_correlation(self.correlation)
        _validate_cleanup(self.cleanup)


@dataclass(frozen=True, slots=True)
class AgentInvocation(Generic[AgentInputT, AgentOutputT, DependenciesT]):
    """Agent definition and application-owned invocation values for one case."""

    agent: Agent[AgentInputT, AgentOutputT, DependenciesT]
    input: AgentInputT
    dependencies: DependenciesT
    history: tuple[AgentMessage, ...] = ()
    correlation: ExecutionCorrelation | None = None
    cleanup: Cleanup | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.agent, Agent):
            raise TypeError("AgentInvocation agent must be an Agent.")
        if not isinstance(self.history, tuple) or any(
            not isinstance(message, AgentMessage) for message in self.history
        ):
            raise TypeError("AgentInvocation history must be a tuple of AgentMessage values.")
        _validate_correlation(self.correlation)
        _validate_cleanup(self.cleanup)


class EvaluationTarget:
    """Runtime interface shared by SDK-owned target declarations."""

    kind: TargetKind
    key: str
    name: str
    input_version: int

    @property
    def input_schema(self) -> dict[str, object]:
        raise NotImplementedError

    def validate_input(self, input_json: object) -> object:
        raise NotImplementedError

    async def execute(
        self,
        input_value: object,
        *,
        context: EvaluationContext,
        service_identity: ExecutionServiceIdentity,
        resources: object,
    ) -> TargetExecution:
        raise NotImplementedError


class _TypedTarget(EvaluationTarget, Generic[InputT]):
    def __init__(
        self,
        *,
        kind: TargetKind,
        key: str,
        name: str,
        input_version: int,
        input_type: TypeForm[InputT],  # ty: ignore[invalid-type-form]
    ) -> None:
        _validate_registration(key=key, version=input_version, label="target")
        _validate_target_name(name)
        self.kind = kind
        self.key = key
        self.name = name
        self.input_version = input_version
        try:
            self._input_adapter = TypeAdapter(input_type)
            self._input_schema = self._input_adapter.json_schema()
        except Exception as error:
            raise TargetContractError(
                f"Unable to construct the input contract for target {key}:v{input_version}."
            ) from error

    @property
    def input_schema(self) -> dict[str, object]:
        return dict(self._input_schema)

    def validate_input(self, input_json: object) -> InputT:
        try:
            return self._input_adapter.validate_python(input_json)
        except ValidationError as error:
            raise TargetContractError(
                f"Input does not match target {self.kind.value}:{self.key}:v{self.input_version}."
            ) from error


class NodeTarget(_TypedTarget[InputT], Generic[InputT, StateT, ResourcesT]):
    """Execute a fresh application Node through ``evaluate_node()``.

    ``key`` is the stable evaluation dispatch identity. ``name`` is the
    human-readable Node name stored with Studio cases and shown in evaluation
    results; it must describe the real application Node rather than repeat the
    registry key.
    """

    def __init__(
        self,
        *,
        key: str,
        name: str,
        input_version: int,
        input_type: TypeForm[InputT],  # ty: ignore[invalid-type-form]
        factory: Callable[
            [InputT, EvaluationContext, ResourcesT],
            NodeInvocation[StateT] | Awaitable[NodeInvocation[StateT]],
        ],
        projector: Callable[
            [NodeEvaluationResult[StateT], InputT, EvaluationContext, ResourcesT],
            object | Awaitable[object],
        ],
    ) -> None:
        super().__init__(
            kind=TargetKind.NODE,
            key=key,
            name=name,
            input_version=input_version,
            input_type=input_type,
        )
        self._factory = factory
        self._projector = projector

    async def execute(
        self,
        input_value: object,
        *,
        context: EvaluationContext,
        service_identity: ExecutionServiceIdentity,
        resources: object,
    ) -> TargetExecution:
        typed_input = cast(InputT, input_value)
        typed_resources = cast(ResourcesT, resources)
        started = perf_counter()
        try:
            invocation = await _resolve(self._factory(typed_input, context, typed_resources))
            if not isinstance(invocation, NodeInvocation):
                raise TypeError("Node target factory must return NodeInvocation.")
        except Exception as error:
            raise _execution_error("Node target setup failed", error, started=started) from error

        execution: SemanticExecutionReference | None = None

        async def operation() -> TargetExecution:
            nonlocal execution
            try:
                result = cast(
                    NodeEvaluationResult[StateT],
                    await evaluate_node(
                        node=invocation.node,
                        store=invocation.store,
                        correlation=invocation.correlation,
                    ),
                )
            except WorkflowExecutionError as error:
                raise _execution_error(
                    "Node target execution failed",
                    error,
                    started=started,
                    execution=service_identity.reference(
                        executable_type=ExecutableType.WORKFLOW,
                        runtime_id=error.run_id,
                    ),
                ) from error
            except Exception as error:
                raise _execution_error(
                    "Node target execution failed",
                    error,
                    started=started,
                ) from error

            execution = service_identity.reference(
                executable_type=ExecutableType.WORKFLOW,
                runtime_id=result.run_id,
            )
            try:
                subject = await _resolve(
                    self._projector(
                        result,
                        typed_input,
                        context,
                        typed_resources,
                    )
                )
            except Exception as error:
                raise _execution_error(
                    "Node target projection failed",
                    error,
                    started=started,
                    execution=execution,
                ) from error
            return TargetExecution(
                subject=subject,
                execution=execution,
                duration_ms=_duration_ms(started),
            )

        try:
            return await _run_with_cleanup(invocation.cleanup, operation)
        except TargetExecutionError:
            raise
        except Exception as error:
            raise _execution_error(
                "Node target cleanup failed",
                error,
                started=started,
                execution=execution,
            ) from error


class WorkflowTarget(_TypedTarget[InputT], Generic[InputT, ResourcesT]):
    """Execute a fresh application Workflow through ``Workflow.execute()``.

    ``key`` is the stable evaluation dispatch identity. ``name`` is the
    human-readable name of the real Workflow stored with Studio cases and
    shown in evaluation results.
    """

    def __init__(
        self,
        *,
        key: str,
        name: str,
        input_version: int,
        input_type: TypeForm[InputT],  # ty: ignore[invalid-type-form]
        factory: Callable[
            [InputT, EvaluationContext, ResourcesT],
            WorkflowInvocation | Awaitable[WorkflowInvocation],
        ],
        projector: Callable[
            [ExecutionResult[Any], InputT, EvaluationContext, ResourcesT],
            object | Awaitable[object],
        ],
    ) -> None:
        super().__init__(
            kind=TargetKind.WORKFLOW,
            key=key,
            name=name,
            input_version=input_version,
            input_type=input_type,
        )
        self._factory = factory
        self._projector = projector

    async def execute(
        self,
        input_value: object,
        *,
        context: EvaluationContext,
        service_identity: ExecutionServiceIdentity,
        resources: object,
    ) -> TargetExecution:
        typed_input = cast(InputT, input_value)
        typed_resources = cast(ResourcesT, resources)
        started = perf_counter()
        try:
            invocation = await _resolve(self._factory(typed_input, context, typed_resources))
            if not isinstance(invocation, WorkflowInvocation):
                raise TypeError("Workflow target factory must return WorkflowInvocation.")
        except Exception as error:
            raise _execution_error(
                "Workflow target setup failed",
                error,
                started=started,
            ) from error

        execution: SemanticExecutionReference | None = None

        async def operation() -> TargetExecution:
            nonlocal execution
            try:
                result = await invocation.workflow.execute(
                    correlation=invocation.correlation,
                )
            except WorkflowExecutionError as error:
                raise _execution_error(
                    "Workflow target execution failed",
                    error,
                    started=started,
                    execution=service_identity.reference(
                        executable_type=ExecutableType.WORKFLOW,
                        runtime_id=error.run_id,
                    ),
                ) from error
            except Exception as error:
                raise _execution_error(
                    "Workflow target execution failed",
                    error,
                    started=started,
                ) from error

            execution = service_identity.reference(
                executable_type=ExecutableType.WORKFLOW,
                runtime_id=result.run_id,
            )
            try:
                subject = await _resolve(
                    self._projector(
                        result,
                        typed_input,
                        context,
                        typed_resources,
                    )
                )
            except Exception as error:
                raise _execution_error(
                    "Workflow target projection failed",
                    error,
                    started=started,
                    execution=execution,
                ) from error
            return TargetExecution(
                subject=subject,
                execution=execution,
                duration_ms=_duration_ms(started),
            )

        try:
            return await _run_with_cleanup(invocation.cleanup, operation)
        except TargetExecutionError:
            raise
        except Exception as error:
            raise _execution_error(
                "Workflow target cleanup failed",
                error,
                started=started,
                execution=execution,
            ) from error


class AgentTarget(
    _TypedTarget[InputT],
    Generic[InputT, AgentInputT, AgentOutputT, DependenciesT, ResourcesT],
):
    """Execute a real application Agent through ``Agent.execute()``.

    ``key`` is the stable evaluation dispatch identity. ``name`` is the
    human-readable name of the real Agent stored with Studio cases and shown
    in evaluation results.
    """

    def __init__(
        self,
        *,
        key: str,
        name: str,
        input_version: int,
        input_type: TypeForm[InputT],  # ty: ignore[invalid-type-form]
        factory: Callable[
            [InputT, EvaluationContext, ResourcesT],
            AgentInvocation[AgentInputT, AgentOutputT, DependenciesT]
            | Awaitable[AgentInvocation[AgentInputT, AgentOutputT, DependenciesT]],
        ],
        projector: Callable[
            [
                AgentExecutionResult[AgentOutputT],
                InputT,
                EvaluationContext,
                ResourcesT,
            ],
            object | Awaitable[object],
        ],
    ) -> None:
        super().__init__(
            kind=TargetKind.AGENT,
            key=key,
            name=name,
            input_version=input_version,
            input_type=input_type,
        )
        self._factory = factory
        self._projector = projector

    async def execute(
        self,
        input_value: object,
        *,
        context: EvaluationContext,
        service_identity: ExecutionServiceIdentity,
        resources: object,
    ) -> TargetExecution:
        typed_input = cast(InputT, input_value)
        typed_resources = cast(ResourcesT, resources)
        started = perf_counter()
        try:
            invocation = await _resolve(self._factory(typed_input, context, typed_resources))
            if not isinstance(invocation, AgentInvocation):
                raise TypeError("Agent target factory must return AgentInvocation.")
        except Exception as error:
            raise _execution_error("Agent target setup failed", error, started=started) from error

        execution: SemanticExecutionReference | None = None

        async def operation() -> TargetExecution:
            nonlocal execution
            try:
                result = await invocation.agent.execute(
                    invocation.input,
                    dependencies=invocation.dependencies,
                    history=invocation.history,
                    correlation=invocation.correlation,
                )
            except AgentExecutionError as error:
                raise _execution_error(
                    "Agent target execution failed",
                    error,
                    started=started,
                    execution=service_identity.reference(
                        executable_type=ExecutableType.AGENT,
                        runtime_id=error.run_id,
                    ),
                ) from error
            except AgentError as error:
                raise _execution_error(
                    "Agent target invocation failed",
                    error,
                    started=started,
                ) from error
            except Exception as error:
                raise _execution_error(
                    "Agent target execution failed",
                    error,
                    started=started,
                ) from error

            execution = service_identity.reference(
                executable_type=ExecutableType.AGENT,
                runtime_id=result.run_id,
            )
            try:
                subject = await _resolve(
                    self._projector(
                        result,
                        typed_input,
                        context,
                        typed_resources,
                    )
                )
            except Exception as error:
                raise _execution_error(
                    "Agent target projection failed",
                    error,
                    started=started,
                    execution=execution,
                ) from error
            return TargetExecution(
                subject=subject,
                execution=execution,
                duration_ms=_duration_ms(started),
            )

        try:
            return await _run_with_cleanup(invocation.cleanup, operation)
        except TargetExecutionError:
            raise
        except Exception as error:
            raise _execution_error(
                "Agent target cleanup failed",
                error,
                started=started,
                execution=execution,
            ) from error


async def _resolve(
    value: CallbackResultT | Awaitable[CallbackResultT],
) -> CallbackResultT:
    if inspect.isawaitable(value):
        return await cast(Awaitable[CallbackResultT], value)
    return cast(CallbackResultT, value)


async def _run_with_cleanup(
    cleanup: Cleanup | None,
    operation: Callable[[], Awaitable[TargetExecution]],
) -> TargetExecution:
    body_error: BaseException | None = None
    try:
        return await operation()
    except BaseException as error:
        body_error = error
        raise
    finally:
        if cleanup is not None:
            try:
                await _resolve(cleanup())
            except Exception:
                if body_error is None:
                    raise


def _execution_error(
    label: str,
    error: BaseException,
    *,
    started: float,
    execution: SemanticExecutionReference | None = None,
) -> TargetExecutionError:
    return TargetExecutionError(
        f"{label}: {type(error).__name__}.",
        execution=execution,
        duration_ms=_duration_ms(started),
    )


def _duration_ms(started: float) -> int:
    return min(86_400_000, max(0, round((perf_counter() - started) * 1_000)))


def _validate_registration(*, key: str, version: int, label: str) -> None:
    if not isinstance(key, str) or not key.strip() or len(key) > 128:
        raise TargetContractError(f"Evaluation {label} key must be a non-empty string of at most 128 characters.")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise TargetContractError(f"Evaluation {label} version must be a positive integer.")


def _validate_target_name(name: str) -> None:
    if not isinstance(name, str) or not name.strip():
        raise TargetContractError("Evaluation target name must be a non-empty string.")
    if name != name.strip():
        raise TargetContractError("Evaluation target name must not contain surrounding whitespace.")
    if len(name.encode("utf-8")) > 256:
        raise TargetContractError("Evaluation target name must be at most 256 UTF-8 bytes.")


def _validate_correlation(correlation: ExecutionCorrelation | None) -> None:
    if correlation is not None and not isinstance(correlation, ExecutionCorrelation):
        raise TypeError("correlation must be ExecutionCorrelation or None.")


def _validate_cleanup(cleanup: Cleanup | None) -> None:
    if cleanup is not None and not callable(cleanup):
        raise TypeError("cleanup must be callable or None.")
