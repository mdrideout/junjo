"""OpenAI function-tool adapters for native Junjo executions."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar, cast

from agents import FunctionTool
from agents.strict_schema import ensure_strict_json_schema
from pydantic import TypeAdapter
from typing_extensions import TypeForm

from ...agent import Agent
from ...agent.messages import AgentMessage
from ...agent.result import AgentExecutionResult
from ...correlation import ExecutionCorrelation
from ...workflow import ExecutionResult, Workflow

InputT = TypeVar("InputT")
AgentInputT = TypeVar("AgentInputT")
AgentOutputT = TypeVar("AgentOutputT")
DependenciesT = TypeVar("DependenciesT")
ResultT = TypeVar("ResultT")
Cleanup = Callable[[], None | Awaitable[None]]


@dataclass(frozen=True, slots=True)
class WorkflowToolInvocation:
    """Fresh Workflow and application-owned lifecycle for one tool call.

    ``workflow`` must be a fresh invocation definition whose Store state is
    isolated from other tool calls. ``correlation`` is passed through to the
    native execution. ``cleanup`` releases only invocation-scoped application
    resources after success, failure, or cancellation.
    """

    workflow: Workflow
    correlation: ExecutionCorrelation | None = None
    cleanup: Cleanup | None = None


@dataclass(frozen=True, slots=True)
class AgentToolInvocation(Generic[AgentInputT, AgentOutputT, DependenciesT]):
    """Fresh native Junjo Agent invocation for one OpenAI function-tool call.

    The application supplies the typed input, dependencies, optional history,
    correlation, and invocation-scoped cleanup. The adapter does not share
    Agent state or dependencies between OpenAI tool calls.
    """

    agent: Agent[AgentInputT, AgentOutputT, DependenciesT]
    input: AgentInputT
    dependencies: DependenciesT
    history: tuple[AgentMessage, ...] = ()
    correlation: ExecutionCorrelation | None = None
    cleanup: Cleanup | None = None


def workflow_as_tool(
    *,
    name: str,
    description: str,
    input_type: TypeForm[InputT],  # ty: ignore[invalid-type-form]
    workflow_factory: Callable[[InputT], WorkflowToolInvocation | Awaitable[WorkflowToolInvocation]],
    output_projector: Callable[
        [ExecutionResult[Any], InputT],
        object | Awaitable[object],
    ],
) -> FunctionTool:
    """Expose a fresh native Junjo Workflow as an OpenAI function tool.

    The returned framework-native ``FunctionTool`` validates each call against
    ``input_type``, requests a fresh invocation from ``workflow_factory``, runs
    the Workflow normally, and projects its real ``ExecutionResult`` through
    ``output_projector``. Cleanup declared by the invocation always runs.

    :param name: Stable OpenAI function-tool name.
    :param description: Model-facing description of when to call the tool.
    :param input_type: Pydantic-compatible input type used to produce the
        strict OpenAI function schema and validate calls.
    :param workflow_factory: Application factory for one fresh Workflow
        invocation.
    :param output_projector: Application mapping from the native execution
        result and validated input to the tool result.
    :return: OpenAI Agents SDK ``FunctionTool``.
    """

    adapter = TypeAdapter(input_type)

    async def invoke(_context: object, input_json: str) -> object:
        input_value = adapter.validate_json(input_json)
        invocation = await _resolve(workflow_factory(input_value))
        if not isinstance(invocation, WorkflowToolInvocation):
            raise TypeError("workflow_factory must return WorkflowToolInvocation.")

        async def execute() -> object:
            result = await invocation.workflow.execute(correlation=invocation.correlation)
            return await _resolve(output_projector(result, input_value))

        return await _run_with_cleanup(invocation.cleanup, execute)

    return FunctionTool(
        name=name,
        description=description,
        params_json_schema=ensure_strict_json_schema(adapter.json_schema()),
        on_invoke_tool=invoke,
        strict_json_schema=True,
    )


def agent_as_tool(
    *,
    name: str,
    description: str,
    input_type: TypeForm[InputT],  # ty: ignore[invalid-type-form]
    agent_factory: Callable[
        [InputT],
        AgentToolInvocation[AgentInputT, AgentOutputT, DependenciesT]
        | Awaitable[AgentToolInvocation[AgentInputT, AgentOutputT, DependenciesT]],
    ],
    output_projector: Callable[
        [AgentExecutionResult[AgentOutputT], InputT],
        object | Awaitable[object],
    ],
) -> FunctionTool:
    """Expose a fresh native Junjo Agent as an OpenAI function tool.

    The returned framework-native ``FunctionTool`` validates each call against
    ``input_type``, requests a fresh invocation from ``agent_factory``, runs
    the Junjo Agent normally, and projects its real ``AgentExecutionResult``
    through ``output_projector``. Cleanup declared by the invocation always
    runs.

    :param name: Stable OpenAI function-tool name.
    :param description: Model-facing description of when to call the tool.
    :param input_type: Pydantic-compatible input type used to produce the
        strict OpenAI function schema and validate calls.
    :param agent_factory: Application factory for one fresh Junjo Agent
        invocation with typed dependencies.
    :param output_projector: Application mapping from the native execution
        result and validated input to the tool result.
    :return: OpenAI Agents SDK ``FunctionTool``.
    """

    adapter = TypeAdapter(input_type)

    async def invoke(_context: object, input_json: str) -> object:
        input_value = adapter.validate_json(input_json)
        invocation = await _resolve(agent_factory(input_value))
        if not isinstance(invocation, AgentToolInvocation):
            raise TypeError("agent_factory must return AgentToolInvocation.")

        async def execute() -> object:
            result = await invocation.agent.execute(
                invocation.input,
                dependencies=invocation.dependencies,
                history=invocation.history,
                correlation=invocation.correlation,
            )
            return await _resolve(output_projector(result, input_value))

        return await _run_with_cleanup(invocation.cleanup, execute)

    return FunctionTool(
        name=name,
        description=description,
        params_json_schema=ensure_strict_json_schema(adapter.json_schema()),
        on_invoke_tool=invoke,
        strict_json_schema=True,
    )


async def _resolve(value: ResultT | Awaitable[ResultT]) -> ResultT:
    if inspect.isawaitable(value):
        return await cast(Awaitable[ResultT], value)
    return value


async def _run_with_cleanup(
    cleanup: Cleanup | None,
    operation: Callable[[], Awaitable[ResultT]],
) -> ResultT:
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
