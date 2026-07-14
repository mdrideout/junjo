"""Reusable immutable Agent definitions."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import rfc8785
from pydantic import TypeAdapter
from typing_extensions import TypeForm

from .._json import (
    JsonBoundaryError,
    normalize_json,
    require_ijson_integer,
    require_ijson_text,
    thaw_json,
)
from ..hooks import Hooks
from ..util import generate_safe_id
from ._schema import schema_for
from .errors import AgentConfigurationError
from .json import FrozenJsonValue
from .messages import AgentMessage
from .model_driver import ModelDriverBinding
from .result import AgentExecutionResult
from .tool import Tool

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")
DependenciesT = TypeVar("DependenciesT")


@dataclass(frozen=True, slots=True)
class AgentLimits:
    """Positive, deterministic bounds for one Agent execution."""

    model_requests: int = 8
    tool_calls: int = 32

    def __post_init__(self) -> None:
        for name, value in (
            ("model_requests", self.model_requests),
            ("tool_calls", self.tool_calls),
        ):
            try:
                require_ijson_integer(value, name, minimum=1)
            except JsonBoundaryError as exc:
                raise AgentConfigurationError(f"{name} must be a portable positive integer.") from exc

    def to_json(self) -> dict[str, int]:
        return {
            "modelRequests": self.model_requests,
            "toolCalls": self.tool_calls,
        }


@dataclass(frozen=True, slots=True, init=False)
class Agent(Generic[InputT, OutputT, DependenciesT]):
    """A reusable typed Agent definition with isolated bounded executions."""

    key: str
    name: str
    instructions: str
    definition_id: str
    structural_id: str
    input_schema: Mapping[str, FrozenJsonValue]
    output_schema: Mapping[str, FrozenJsonValue]
    input_adapter: TypeAdapter[InputT]
    output_adapter: TypeAdapter[OutputT]
    model: ModelDriverBinding
    tools: tuple[Tool[Any, Any, DependenciesT], ...]
    limits: AgentLimits
    hooks: Hooks | None

    def __init__(
        self,
        *,
        key: str,
        name: str,
        instructions: str,
        input_type: TypeForm[InputT],  # ty: ignore[invalid-type-form]
        model: ModelDriverBinding,
        tools: Sequence[Tool[Any, Any, DependenciesT]],
        output_type: TypeForm[OutputT],  # ty: ignore[invalid-type-form]
        limits: AgentLimits | None = None,
        hooks: Hooks | None = None,
    ) -> None:
        """Declare one immutable, reusable Agent definition.

        Construction validates all boundary schemas and computes the
        language-neutral structural fingerprint. It does not create a driver,
        Store, span, or run identity.

        :param key: Stable application-owned semantic key.
        :param name: Human-readable span and diagnostic name.
        :param instructions: Exact provider-neutral instructions.
        :param input_type: Pydantic-compatible input boundary type.
        :param model: Descriptor plus shared driver or per-run factory.
        :param tools: Ordered Tool definitions available to the model.
        :param output_type: Pydantic-compatible successful output type.
        :param limits: Positive per-execution limits; defaults are explicit.
        :param hooks: Optional lifecycle observers. Hooks do not own execution.
        :raises AgentConfigurationError: If any declaration is invalid.
        """
        _validate_identity(key=key, name=name, instructions=instructions)
        _validate_model_and_hooks(model=model, hooks=hooks)
        effective_limits = _effective_limits(limits)
        declared_tools = _validated_tools(tools)
        input_adapter, output_adapter, input_schema, output_schema = _boundary_contracts(
            input_type=input_type,
            output_type=output_type,
        )

        material = _structural_material(
            key=key,
            instructions=instructions,
            input_schema=input_schema,
            model=model,
            tools=declared_tools,
            output_schema=output_schema,
            limits=effective_limits,
        )
        try:
            canonical = rfc8785.dumps(normalize_json(material))
        except Exception as exc:
            raise AgentConfigurationError("Agent structural material must be bounded, canonicalizable I-JSON.") from exc
        structural_id = f"agent_sha256:{hashlib.sha256(canonical).hexdigest()}"

        object.__setattr__(self, "key", key)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "instructions", instructions)
        object.__setattr__(self, "definition_id", generate_safe_id())
        object.__setattr__(self, "structural_id", structural_id)
        object.__setattr__(self, "input_schema", input_schema)
        object.__setattr__(self, "output_schema", output_schema)
        object.__setattr__(self, "input_adapter", input_adapter)
        object.__setattr__(self, "output_adapter", output_adapter)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "tools", declared_tools)
        object.__setattr__(self, "limits", effective_limits)
        object.__setattr__(self, "hooks", hooks)

    def structural_material(self) -> dict[str, object]:
        """Return the exact pre-policy material used for this fingerprint."""

        return _structural_material(
            key=self.key,
            instructions=self.instructions,
            input_schema=self.input_schema,
            model=self.model,
            tools=self.tools,
            output_schema=self.output_schema,
            limits=self.limits,
        )

    def definition_snapshot(self) -> dict[str, object]:
        """Return schema-versioned diagnostic definition evidence."""

        return {
            "v": 1,
            "agentKey": self.key,
            "name": self.name,
            "instructions": self.instructions,
            "inputSchema": thaw_json(self.input_schema),
            "model": self.model.descriptor.to_json(),
            "tools": [tool.definition_snapshot() for tool in self.tools],
            "outputSchema": thaw_json(self.output_schema),
            "limits": self.limits.to_json(),
            "structuralId": self.structural_id,
        }

    async def execute(
        self,
        input: InputT,
        *,
        dependencies: DependenciesT,
        history: Sequence[AgentMessage] = (),
    ) -> AgentExecutionResult[OutputT]:
        """Execute one isolated run against detached typed boundaries.

        :param input: Value validated against ``input_type``.
        :param dependencies: Opaque application-owned services passed only to
            Tool contexts.
        :param history: Complete prior normalized exchanges. Junjo does not
            persist history between calls.
        :returns: A detached successful result whose output is ``OutputT``.
        :raises AgentInvocationError: If admission boundaries are invalid.
        :raises AgentExecutionError: If admitted execution fails.
        :raises asyncio.CancelledError: If the caller cancels active work.
        """

        from ._runtime import execute_agent

        return await execute_agent(
            self,
            input=input,
            dependencies=dependencies,
            history=history,
        )


def _structural_material(
    *,
    key: str,
    instructions: str,
    input_schema: Mapping[str, FrozenJsonValue],
    model: ModelDriverBinding,
    tools: Sequence[Tool],
    output_schema: Mapping[str, FrozenJsonValue],
    limits: AgentLimits,
) -> dict[str, object]:
    return {
        "v": 1,
        "agentKey": key,
        "instructions": instructions,
        "inputSchema": thaw_json(input_schema),
        "model": model.descriptor.to_json(),
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": thaw_json(tool.input_schema),
                "outputSchema": thaw_json(tool.output_schema),
            }
            for tool in tools
        ],
        "outputSchema": thaw_json(output_schema),
        "limits": limits.to_json(),
    }


def _validate_identity(*, key: object, name: object, instructions: object) -> None:
    try:
        require_ijson_text(key, "Agent key", nonempty=True)
        require_ijson_text(name, "Agent name", nonempty=True)
        require_ijson_text(instructions, "Agent instructions")
    except JsonBoundaryError as exc:
        raise AgentConfigurationError(str(exc)) from exc


def _validate_model_and_hooks(*, model: object, hooks: object) -> None:
    if not isinstance(model, ModelDriverBinding):
        raise AgentConfigurationError("model must be a ModelDriverBinding.")
    if hooks is not None and not isinstance(hooks, Hooks):
        raise AgentConfigurationError("hooks must be Hooks or None.")


def _effective_limits(limits: AgentLimits | None) -> AgentLimits:
    effective = limits if limits is not None else AgentLimits()
    if not isinstance(effective, AgentLimits):
        raise AgentConfigurationError("limits must be AgentLimits.")
    return effective


def _validated_tools(
    tools: Sequence[Tool[Any, Any, DependenciesT]],
) -> tuple[Tool[Any, Any, DependenciesT], ...]:
    declared = tuple(tools)
    if any(not isinstance(tool, Tool) for tool in declared):
        raise AgentConfigurationError("tools must contain only Tool definitions.")
    names = [tool.name for tool in declared]
    if len(names) != len(set(names)):
        raise AgentConfigurationError("Tool names must be unique within an Agent.")
    return declared


def _boundary_contracts(
    *,
    input_type: TypeForm[InputT],  # ty: ignore[invalid-type-form]
    output_type: TypeForm[OutputT],  # ty: ignore[invalid-type-form]
) -> tuple[
    TypeAdapter[InputT],
    TypeAdapter[OutputT],
    Mapping[str, FrozenJsonValue],
    Mapping[str, FrozenJsonValue],
]:
    try:
        input_adapter = TypeAdapter(input_type)
        output_adapter = TypeAdapter(output_type)
        input_schema = schema_for(input_adapter)
        output_schema = schema_for(output_adapter)
    except Exception as exc:
        raise AgentConfigurationError(
            "Agent boundary types must be schema-capable and have identical "
            "normalized validation and serialization schemas."
        ) from exc
    return input_adapter, output_adapter, input_schema, output_schema
