"""Explicit typed Tool definitions and service boundaries."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Generic, Protocol, TypeAlias, TypeVar

import rfc8785
from pydantic import TypeAdapter
from typing_extensions import TypeForm

from .._json import JsonBoundaryError, normalize_json, require_ijson_text, thaw_json
from ._schema import schema_for, schema_proves_object_root
from .errors import ToolConfigurationError
from .json import FrozenJsonValue

DependenciesT = TypeVar("DependenciesT")
ToolInputT = TypeVar("ToolInputT")
ToolOutputT = TypeVar("ToolOutputT")

TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")


@dataclass(frozen=True, slots=True)
class AgentRunContext(Generic[DependenciesT]):
    """Read-only Agent identity and opaque dependencies supplied to a Tool."""

    dependencies: DependenciesT
    agent_key: str
    definition_id: str
    run_id: str
    tool_call_id: str
    call_ordinal: int


class ToolService(Protocol[ToolInputT, ToolOutputT, DependenciesT]):
    """Asynchronous application capability invoked by the Agent runtime."""

    async def __call__(
        self,
        input: ToolInputT,
        context: AgentRunContext[DependenciesT],
    ) -> ToolOutputT: ...


ToolServiceFactory: TypeAlias = Callable[[], ToolService[ToolInputT, ToolOutputT, DependenciesT]]


@dataclass(frozen=True, slots=True, init=False)
class Tool(Generic[ToolInputT, ToolOutputT, DependenciesT]):
    """Immutable typed capability declaration available to an Agent."""

    name: str
    description: str
    input_schema: Mapping[str, FrozenJsonValue]
    output_schema: Mapping[str, FrozenJsonValue]
    structural_id: str
    input_adapter: TypeAdapter[ToolInputT]
    output_adapter: TypeAdapter[ToolOutputT]
    shared_service: ToolService[ToolInputT, ToolOutputT, DependenciesT] | None
    factory: ToolServiceFactory[ToolInputT, ToolOutputT, DependenciesT] | None

    def __init__(
        self,
        *,
        name: str,
        description: str,
        input_type: TypeForm[ToolInputT],  # ty: ignore[invalid-type-form]
        output_type: TypeForm[ToolOutputT],  # ty: ignore[invalid-type-form]
        shared_service: ToolService[ToolInputT, ToolOutputT, DependenciesT] | None = None,
        factory: ToolServiceFactory[ToolInputT, ToolOutputT, DependenciesT] | None = None,
    ) -> None:
        """Declare one typed Tool and exactly one service ownership mode.

        :param name: Unique model-facing Tool name.
        :param description: Model-facing description included in requests.
        :param input_type: Object-root Pydantic-compatible argument type.
        :param output_type: Pydantic-compatible result type.
        :param shared_service: Caller-guaranteed concurrency-safe service.
        :param factory: Synchronous factory invoked once per admitted Agent
            run, lazily before the Tool's first service call.
        :raises ToolConfigurationError: If schemas, identity, or service
            ownership are invalid.
        """
        if not isinstance(name, str) or TOOL_NAME_PATTERN.fullmatch(name) is None:
            raise ToolConfigurationError("Tool name must match ^[A-Za-z_][A-Za-z0-9_-]{0,63}$.")
        try:
            require_ijson_text(description, "Tool description", nonempty=True)
        except JsonBoundaryError as exc:
            raise ToolConfigurationError(str(exc)) from exc
        if (shared_service is None) == (factory is None):
            raise ToolConfigurationError("Tool requires exactly one shared_service or factory.")
        if shared_service is not None and not callable(shared_service):
            raise ToolConfigurationError("shared_service must be callable.")
        if factory is not None and not callable(factory):
            raise ToolConfigurationError("factory must be callable.")

        try:
            input_adapter = TypeAdapter(input_type)
            output_adapter = TypeAdapter(output_type)
            input_schema = schema_for(input_adapter)
            output_schema = schema_for(output_adapter)
        except Exception as exc:
            raise ToolConfigurationError(
                "Tool boundary types must be schema-capable and have identical "
                "normalized validation and serialization schemas."
            ) from exc
        if not isinstance(input_schema, Mapping) or not schema_proves_object_root(input_schema):
            raise ToolConfigurationError("Tool input_type must produce an object-root JSON Schema.")

        material = {
            "v": 1,
            "name": name,
            "description": description,
            "inputSchema": thaw_json(input_schema),
            "outputSchema": thaw_json(output_schema),
        }
        try:
            canonical = rfc8785.dumps(normalize_json(material))
        except Exception as exc:
            raise ToolConfigurationError("Tool structural material must be bounded, canonicalizable I-JSON.") from exc
        structural_id = f"tool_sha256:{hashlib.sha256(canonical).hexdigest()}"

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "input_schema", input_schema)
        object.__setattr__(self, "output_schema", output_schema)
        object.__setattr__(self, "structural_id", structural_id)
        object.__setattr__(self, "input_adapter", input_adapter)
        object.__setattr__(self, "output_adapter", output_adapter)
        object.__setattr__(self, "shared_service", shared_service)
        object.__setattr__(self, "factory", factory)

    def structural_material(self) -> dict[str, object]:
        return {
            "v": 1,
            "name": self.name,
            "description": self.description,
            "inputSchema": thaw_json(self.input_schema),
            "outputSchema": thaw_json(self.output_schema),
        }

    def definition_snapshot(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "structuralId": self.structural_id,
            "inputSchema": thaw_json(self.input_schema),
            "outputSchema": thaw_json(self.output_schema),
        }
