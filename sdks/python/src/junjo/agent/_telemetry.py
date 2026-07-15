"""OpenTelemetry evidence helpers for the provider-neutral Agent runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from opentelemetry.trace import Span

from .._identity import ParentExecutableIdentity
from .._json import thaw_json
from ..telemetry.otel_schema import JUNJO_TELEMETRY_CONTRACT_VERSION
from ..telemetry.payload import encode_json, set_full_payload
from ._boundary import json_candidate
from .json import JsonValue
from .messages import ModelResponse, response_to_json
from .result import AgentUsage

if TYPE_CHECKING:
    from .definition import Agent
    from .tool import Tool


def initialize_agent_span(
    span: Span,
    *,
    agent: Agent,
    run_id: str,
    parent: ParentExecutableIdentity | None,
) -> None:
    """Attach definition and stable execution identity before boundary admission."""

    span.set_attribute("junjo.telemetry.contract_version", JUNJO_TELEMETRY_CONTRACT_VERSION)
    span.set_attribute("junjo.span_type", "agent")
    span.set_attribute("junjo.executable_definition_id", agent.definition_id)
    span.set_attribute("junjo.executable_runtime_id", run_id)
    span.set_attribute("junjo.executable_structural_id", agent.structural_id)
    span.set_attribute("junjo.agent.key", agent.key)
    span.set_attribute("junjo.agent.name", agent.name)
    span.set_attribute("junjo.agent.runtime_id", run_id)
    span.set_attribute("junjo.agent.state.available", False)
    span.set_attribute("junjo.agent.limit.model_requests", agent.limits.model_requests)
    span.set_attribute("junjo.agent.limit.tool_calls", agent.limits.tool_calls)
    set_full_payload(
        span,
        "junjo.agent.definition_snapshot",
        agent.definition_snapshot(),
    )
    if parent is not None:
        span.set_attribute(
            "junjo.parent_executable_definition_id",
            parent.executable_definition_id,
        )
        span.set_attribute(
            "junjo.parent_executable_runtime_id",
            parent.executable_runtime_id,
        )
        span.set_attribute(
            "junjo.parent_executable_structural_id",
            parent.executable_structural_id,
        )
        span.set_attribute("junjo.parent_executable_type", parent.executable_type.value)


def initialize_model_span(
    span: Span,
    *,
    agent: Agent,
    run_id: str,
    sequence: int,
    ordinal: int,
) -> None:
    descriptor = agent.model.descriptor
    span.set_attribute("junjo.telemetry.contract_version", JUNJO_TELEMETRY_CONTRACT_VERSION)
    span.set_attribute("junjo.agent.operation_type", "model_request")
    span.set_attribute("junjo.agent.key", agent.key)
    span.set_attribute("junjo.agent.runtime_id", run_id)
    span.set_attribute("junjo.agent.operation.sequence", sequence)
    span.set_attribute("junjo.agent.model_request.ordinal", ordinal)
    span.set_attribute("junjo.agent.model.driver_key", descriptor.driver_key)
    span.set_attribute("junjo.agent.model.provider", descriptor.provider)
    span.set_attribute("junjo.agent.model.name", descriptor.model)


def initialize_tool_span(
    span: Span,
    *,
    agent_key: str,
    run_id: str,
    sequence: int,
    tool: Tool,
    call_id: str,
    call_ordinal: int,
    requested_arguments: object,
) -> None:
    span.set_attribute("junjo.telemetry.contract_version", JUNJO_TELEMETRY_CONTRACT_VERSION)
    span.set_attribute("junjo.agent.operation_type", "tool")
    span.set_attribute("junjo.agent.key", agent_key)
    span.set_attribute("junjo.agent.runtime_id", run_id)
    span.set_attribute("junjo.agent.operation.sequence", sequence)
    span.set_attribute("junjo.agent.tool_call.id", call_id)
    span.set_attribute("junjo.agent.tool_call.ordinal", call_ordinal)
    span.set_attribute("junjo.agent.tool.name", tool.name)
    span.set_attribute("junjo.agent.tool.structural_id", tool.structural_id)
    set_full_payload(
        span,
        "junjo.agent.tool.requested_arguments",
        requested_arguments,
    )


def record_candidate(
    span: Span,
    *,
    availability_root: str,
    payload_root: str,
    candidate: object,
) -> JsonValue | None:
    """Capture a safe diagnostic candidate without applying a declared schema."""

    normalized = diagnostic_candidate(candidate)
    if normalized is None:
        span.set_attribute(availability_root, False)
        span.set_attribute(
            _unavailable_reason_attribute(availability_root),
            "not_json_serializable",
        )
        return None
    span.set_attribute(availability_root, True)
    set_full_payload(span, payload_root, normalized)
    return normalized


def diagnostic_candidate(candidate: object) -> JsonValue | None:
    """Return truthful concrete diagnostic JSON without publishing evidence."""

    try:
        if isinstance(candidate, ModelResponse):
            normalized: JsonValue = response_to_json(candidate)
        else:
            normalized = thaw_json(json_candidate(candidate))
    except Exception:
        return None
    return normalized


def record_unavailable(
    span: Span,
    *,
    availability_root: str,
    reason: str,
) -> None:
    span.set_attribute(availability_root, False)
    span.set_attribute(_unavailable_reason_attribute(availability_root), reason)


def _unavailable_reason_attribute(availability_root: str) -> str:
    suffix = ".available"
    if not availability_root.endswith(suffix):
        raise ValueError("Candidate availability attributes must end with '.available'.")
    return f"{availability_root.removesuffix(suffix)}.unavailable_reason"


def record_model_response(
    span: Span,
    response: ModelResponse,
) -> None:
    span.set_attribute("junjo.agent.model.response_type", response.type)
    set_full_payload(span, "junjo.agent.model.response", response_to_json(response))
    if response.usage is not None:
        span.set_attribute("junjo.agent.model.usage", encode_json(response.usage.to_json()))


def finalize_agent_counts(
    span: Span,
    *,
    operation_count: int,
    model_request_count: int,
    tool_call_requested_count: int,
    tool_call_admitted_count: int,
    tool_call_started_count: int,
    tool_call_completed_count: int,
    usage: AgentUsage,
) -> None:
    span.set_attribute("junjo.agent.operation.count", operation_count)
    span.set_attribute("junjo.agent.model_request.count", model_request_count)
    span.set_attribute(
        "junjo.agent.tool_call.requested_count",
        tool_call_requested_count,
    )
    span.set_attribute(
        "junjo.agent.tool_call.admitted_count",
        tool_call_admitted_count,
    )
    span.set_attribute(
        "junjo.agent.tool_call.started_count",
        tool_call_started_count,
    )
    span.set_attribute(
        "junjo.agent.tool_call.completed_count",
        tool_call_completed_count,
    )
    span.set_attribute("junjo.agent.usage", encode_json(usage.to_json()))


def attributes_from_mapping(
    span: Span,
    attributes: Mapping[str, str | int | bool],
) -> None:
    for name, value in attributes.items():
        span.set_attribute(name, value)
