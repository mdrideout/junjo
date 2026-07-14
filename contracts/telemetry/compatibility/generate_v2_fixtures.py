#!/usr/bin/env python3
"""Generate deterministic telemetry-v2 fixtures from compact scenario builders."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from canonical_json import dumps as canonical_json_dumps
from schema_normalization import normalize_generated_schema

CONTRACT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = CONTRACT_ROOT / "fixtures" / "workflow"
FULL_POLICY = "junjo.full.v1"
AGENT_PRODUCER_ROOT = CONTRACT_ROOT / "fixtures" / "agent" / "producer"
AGENT_CONSUMER_ROOT = CONTRACT_ROOT / "fixtures" / "agent" / "consumer"
INVALID_AGENT_ROOT = CONTRACT_ROOT / "fixtures" / "invalid" / "agent"
FINGERPRINT_ROOT = CONTRACT_ROOT / "fixtures" / "fingerprints"
STORE_FIXTURE_ROOT = CONTRACT_ROOT / "fixtures" / "store"

AGENT_PRODUCER_SCENARIOS = (
    "direct_typed_completion",
    "standalone_agent_under_non_junjo_span",
    "ordered_multiple_tools",
    "multi_tool_first_failure",
    "multi_tool_first_cancellation",
    "tool_invokes_nested_workflow",
    "agent_inside_workflow_node",
    "nested_workflow_failure",
    "agent_failure_inside_workflow_node",
    "agent_cancellation_inside_workflow_node",
    "boundary_input_history_rejection",
    "unknown_tool",
    "malformed_tool_arguments",
    "malformed_model_response",
    "nonserializable_model_response_candidate",
    "model_driver_failure",
    "tool_service_failure",
    "tool_output_validation_failure",
    "nonserializable_tool_result_candidate",
    "final_output_validation_failure",
    "over_budget_tool_batch",
    "model_request_limit_exhaustion",
    "cancelled_model_request",
    "cancelled_tool_service",
    "cancelled_workflow_tool",
    "concurrent_run_isolation",
    "usage_absent_vs_zero",
    "hook_failure_then_success",
    "terminal_observer_cancellation",
    "nested_agent_owner_isolation",
    "admission_internal_error",
    "terminal_commit_internal_error_partial",
    "unexpected_internal_error",
)
AGENT_CONSUMER_SCENARIOS = (
    "nonfull_payload_modes",
    "redacted_operation_payloads",
    "policy_unavailable_store",
    "dropped_evidence_partial",
)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _decode_pointer_token(value: str) -> str:
    return value.replace("~1", "/").replace("~0", "~")


def _apply_patch(document: Any, operations: list[dict[str, Any]]) -> Any:
    result = copy.deepcopy(document)
    for operation in operations:
        path = operation["path"]
        if path == "":
            if operation["op"] in {"add", "replace"}:
                result = copy.deepcopy(operation["value"])
                continue
            raise ValueError("root remove is not used by canonical Workflow fixtures")
        tokens = [_decode_pointer_token(token) for token in path.lstrip("/").split("/")]
        parent = result
        for token in tokens[:-1]:
            parent = parent[int(token)] if isinstance(parent, list) else parent[token]
        leaf = tokens[-1]
        if operation["op"] in {"add", "replace"}:
            value = copy.deepcopy(operation["value"])
            if isinstance(parent, list):
                if leaf == "-":
                    parent.append(value)
                elif operation["op"] == "add":
                    parent.insert(int(leaf), value)
                else:
                    parent[int(leaf)] = value
            else:
                parent[leaf] = value
        elif operation["op"] == "remove":
            if isinstance(parent, list):
                del parent[int(leaf)]
            else:
                del parent[leaf]
        else:
            raise ValueError(f"unsupported canonical patch operation: {operation['op']}")
    return result


def migrate_workflow_fixtures() -> None:
    """Upgrade the six accepted Workflow fixtures to the v2 evidence envelope."""
    for path in sorted(WORKFLOW_ROOT.glob("*.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        fixture["contract_version"] = 2

        for span in fixture["spans"]:
            span["resource_attributes_json"] = {
                "service.name": span["service_name"],
                "service.namespace": "junjo.contract",
                "service.version": "2.0.0",
            }
            span["resource_dropped_attributes_count"] = 0
            span["dropped_attributes_count"] = 0
            span["dropped_events_count"] = 0
            span["dropped_links_count"] = 0
            attributes = span["attributes_json"]
            if "junjo.telemetry.contract_version" in attributes:
                attributes["junjo.telemetry.contract_version"] = 2
            for event in span["events_json"]:
                event["timeUnixNano"] = str(event["timeUnixNano"])
                event["droppedAttributesCount"] = 0

        owners_by_store: dict[str, dict[str, Any]] = {}
        transitions_by_store: dict[str, list[dict[str, Any]]] = {}
        for span in fixture["spans"]:
            attributes = span["attributes_json"]
            store_id = attributes.get("junjo.workflow.store.id")
            if store_id:
                owners_by_store[store_id] = span
            for event in span["events_json"]:
                if event["name"] != "set_state":
                    continue
                event_store_id = event["attributes"].get("junjo.store.id")
                if event_store_id:
                    transitions_by_store.setdefault(event_store_id, []).append(event)

        for store_id, owner in owners_by_store.items():
            attributes = owner["attributes_json"]
            start_raw = attributes["junjo.workflow.state.start"]
            start_state = json.loads(start_raw)
            current_state = copy.deepcopy(start_state)
            revision = 0
            transitions = sorted(
                transitions_by_store.get(store_id, []),
                key=lambda event: int(event["timeUnixNano"]),
            )
            for sequence, event in enumerate(transitions, start=1):
                event_attributes = event["attributes"]
                patch = json.loads(event_attributes["junjo.state_json_patch"])
                next_state = _apply_patch(current_state, patch)
                revision_before = revision
                if next_state != current_state:
                    revision += 1
                else:
                    patch = []
                    event_attributes["junjo.state_json_patch"] = "[]"
                event_attributes.update(
                    {
                        "junjo.store.transition.sequence": sequence,
                        "junjo.store.revision.before": revision_before,
                        "junjo.store.revision.after": revision,
                        "junjo.state_json_patch.mode": "full",
                        "junjo.state_json_patch.policy": FULL_POLICY,
                    }
                )
                current_state = next_state

            attributes.update(
                {
                    "junjo.workflow.state.start.mode": "full",
                    "junjo.workflow.state.start.policy": FULL_POLICY,
                    "junjo.workflow.state.end": json.dumps(
                        current_state, separators=(",", ":"), ensure_ascii=False
                    ),
                    "junjo.workflow.state.end.mode": "full",
                    "junjo.workflow.state.end.policy": FULL_POLICY,
                    "junjo.store.revision.start": 0,
                    "junjo.store.revision.end": revision,
                    "junjo.store.transition.count": len(transitions),
                    "junjo.store.reconstructable": True,
                }
            )

        _write(path, fixture)


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _hex(seed: str, length: int) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:length]


def _payload(attributes: dict[str, Any], root: str, value: Any, mode: str = "full") -> None:
    attributes[f"{root}.mode"] = mode
    attributes[f"{root}.policy"] = FULL_POLICY
    if mode in {"full", "redacted"}:
        attributes[root] = _json(value)
    elif mode == "reference":
        attributes[f"{root}.reference"] = f"fixture://{_hex(root, 16)}"


def _resource(service_name: str, version: str = "2.0.0") -> dict[str, Any]:
    return {
        "service.name": service_name,
        "service.namespace": "junjo.contract",
        "service.version": version,
    }


def _span(
    scenario: str,
    index: int,
    service_name: str,
    trace_id: str,
    name: str,
    parent_span_id: str | None,
    attributes: dict[str, Any],
    *,
    events: list[dict[str, Any]] | None = None,
    status_code: str = "0",
    status_message: str = "",
) -> dict[str, Any]:
    second = index // 1000
    microsecond = (index % 1000) * 1000
    return {
        "trace_id": trace_id,
        "span_id": _hex(f"{scenario}:span:{index}", 16),
        "parent_span_id": parent_span_id,
        "service_name": service_name,
        "resource_attributes_json": _resource(service_name),
        "resource_dropped_attributes_count": 0,
        "name": name,
        "kind": "INTERNAL",
        "start_time": f"2026-07-13T12:00:{second:02d}.{microsecond:06d}+00:00",
        "end_time": f"2026-07-13T12:00:{second:02d}.{microsecond + 500:06d}+00:00",
        "status_code": status_code,
        "status_message": status_message,
        "attributes_json": attributes,
        "events_json": events or [],
        "links_json": [],
        "trace_flags": 1,
        "trace_state": "junjo=fixture",
        "dropped_attributes_count": 0,
        "dropped_events_count": 0,
        "dropped_links_count": 0,
    }


def _tool_material(name: str = "lookup") -> dict[str, Any]:
    return {
        "v": 1,
        "name": name,
        "description": f"Run {name}",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
        "outputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["value"],
            "properties": {"value": {"type": "string"}},
        },
    }


def _structural_id(prefix: str, material: dict[str, Any]) -> str:
    canonical = canonical_json_dumps(material)
    return f"{prefix}_sha256:{hashlib.sha256(canonical).hexdigest()}"


def _agent_material(
    agent_key: str = "fixture_agent",
    tool_names: tuple[str, ...] = ("lookup",),
    *,
    model_request_limit: int = 4,
    tool_call_limit: int = 4,
) -> dict[str, Any]:
    return {
        "v": 1,
        "agentKey": agent_key,
        "instructions": "Answer with deterministic fixture evidence.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["question"],
            "properties": {"question": {"type": "string"}},
        },
        "model": {
            "driverKey": "scripted",
            "provider": "junjo",
            "model": "scripted-v1",
            "settings": {},
        },
        "tools": [
            {key: value for key, value in _tool_material(name).items() if key != "v"}
            for name in tool_names
        ],
        "outputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer"],
            "properties": {"answer": {"type": "string"}},
        },
        "limits": {
            "modelRequests": model_request_limit,
            "toolCalls": tool_call_limit,
        },
    }


def _definition(
    agent_key: str,
    agent_name: str,
    tool_names: tuple[str, ...],
    *,
    model_request_limit: int,
    tool_call_limit: int,
) -> tuple[dict[str, Any], str]:
    material = _agent_material(
        agent_key,
        tool_names,
        model_request_limit=model_request_limit,
        tool_call_limit=tool_call_limit,
    )
    structural_id = _structural_id("agent", material)
    snapshot = {
        "v": 1,
        "agentKey": agent_key,
        "name": agent_name,
        "instructions": material["instructions"],
        "inputSchema": material["inputSchema"],
        "model": material["model"],
        "tools": [
            {
                "name": tool["name"],
                "description": tool["description"],
                "structuralId": _structural_id("tool", {"v": 1, **tool}),
                "inputSchema": tool["inputSchema"],
                "outputSchema": tool["outputSchema"],
            }
            for tool in material["tools"]
        ],
        "outputSchema": material["outputSchema"],
        "limits": material["limits"],
        "structuralId": structural_id,
    }
    return snapshot, structural_id


def _usage(model_responses: int, *, reported: bool = True) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if reported and model_responses:
        fields = {
            "inputTokens": {"sum": 10 * model_responses, "observations": model_responses},
            "outputTokens": {"sum": 4 * model_responses, "observations": model_responses},
            "totalTokens": {"sum": 14 * model_responses, "observations": model_responses},
        }
    return {"v": 1, "modelResponses": model_responses, "fields": fields}


def _model_request(run_id: str, ordinal: int, tool_names: tuple[str, ...]) -> dict[str, Any]:
    return {
        "v": 1,
        "agentKey": "fixture_agent",
        "runId": run_id,
        "ordinal": ordinal,
        "instructions": "Answer with deterministic fixture evidence.",
        "messages": [{"type": "agent_input", "input": {"question": "fixture?"}}],
        "tools": [
            {
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": tool["inputSchema"],
                "outputSchema": tool["outputSchema"],
            }
            for tool in (_tool_material(name) for name in tool_names)
        ],
        "outputSchema": _agent_material()["outputSchema"],
    }


def _exception_event(error_type: str, message: str, time_ns: int) -> dict[str, Any]:
    return {
        "name": "exception",
        "timeUnixNano": str(time_ns),
        "attributes": {
            "exception.type": error_type,
            "exception.message": message,
            "exception.stacktrace": f"{error_type}: {message}",
        },
        "droppedAttributesCount": 0,
    }


def _base_agent_case(
    scenario: str,
    *,
    requested_tools: tuple[str, ...] = (),
    observed_tools: int | None = None,
    final_model: bool = True,
    outcome: str = "completed",
    reason: str = "final_output",
    model_request_limit: int = 4,
    tool_call_limit: int = 4,
) -> dict[str, Any]:
    service_name = f"svc-agent-{scenario.replace('_', '-')}"
    trace_id = _hex(f"{scenario}:trace", 32)
    agent_key = "fixture_agent"
    agent_name = "Fixture Agent"
    declared_tools = tuple(dict.fromkeys(name for name in requested_tools if name != "missing")) or ("lookup",)
    definition, structural_id = _definition(
        agent_key,
        agent_name,
        declared_tools,
        model_request_limit=model_request_limit,
        tool_call_limit=tool_call_limit,
    )
    run_id = f"run-{_hex(scenario, 20)}"
    definition_id = f"definition-{_hex(scenario, 16)}"
    agent_span_id = _hex(f"{scenario}:span:0", 16)
    spans: list[dict[str, Any]] = []
    operation_index = 1
    model_ordinal = 1
    tool_ordinal = 0
    operation_spans: list[dict[str, Any]] = []
    validated_model_responses = 0

    calls = [
        {"id": f"call-{index + 1}", "name": name, "arguments": {"query": f"q{index + 1}"}}
        for index, name in enumerate(requested_tools)
    ]
    first_response = (
        {"v": 1, "type": "tool_calls", "assistantText": "Using tools", "calls": calls, "usage": {"v": 1, "inputTokens": 10, "outputTokens": 4, "totalTokens": 14}}
        if calls
        else {"v": 1, "type": "final_output", "output": {"answer": "done"}, "usage": {"v": 1, "inputTokens": 10, "outputTokens": 4, "totalTokens": 14}}
    )
    model_attributes: dict[str, Any] = {
        "junjo.telemetry.contract_version": 2,
        "junjo.agent.operation_type": "model_request",
        "junjo.agent.key": agent_key,
        "junjo.agent.runtime_id": run_id,
        "junjo.agent.operation.sequence": operation_index,
        "junjo.agent.model_request.ordinal": model_ordinal,
        "junjo.agent.model_request.state_revision": 0,
        "junjo.agent.model.driver_key": "scripted",
        "junjo.agent.model.provider": "junjo",
        "junjo.agent.model.name": "scripted-v1",
        "junjo.agent.model.response_candidate.available": True,
        "junjo.agent.model.response_type": first_response["type"],
        "junjo.agent.model.usage": _json(first_response["usage"]),
    }
    _payload(model_attributes, "junjo.agent.model.request", _model_request(run_id, 1, declared_tools))
    _payload(model_attributes, "junjo.agent.model.response_candidate", first_response)
    _payload(model_attributes, "junjo.agent.model.response", first_response)
    operation_spans.append(
        _span(scenario, operation_index, service_name, trace_id, "model request 1", agent_span_id, model_attributes)
    )
    operation_index += 1
    validated_model_responses += 1

    observed_count = len(calls) if observed_tools is None else observed_tools
    for index, call in enumerate(calls[:observed_count], start=1):
        tool_ordinal += 1
        material = _tool_material(call["name"] if call["name"] != "missing" else "lookup")
        tool_attributes: dict[str, Any] = {
            "junjo.telemetry.contract_version": 2,
            "junjo.agent.operation_type": "tool",
            "junjo.agent.key": agent_key,
            "junjo.agent.runtime_id": run_id,
            "junjo.agent.operation.sequence": operation_index,
            "junjo.agent.tool_call.id": call["id"],
            "junjo.agent.tool_call.ordinal": tool_ordinal,
            "junjo.agent.tool.name": call["name"],
            "junjo.agent.tool.structural_id": _structural_id("tool", material),
            "junjo.agent.tool.state_revision.before": 0,
            "junjo.agent.tool.state_revision.after": 0,
            "junjo.agent.tool.result_candidate.available": True,
        }
        _payload(tool_attributes, "junjo.agent.tool.requested_arguments", call["arguments"])
        _payload(tool_attributes, "junjo.agent.tool.arguments", call["arguments"])
        result = {"value": f"result-{index}"}
        _payload(tool_attributes, "junjo.agent.tool.result_candidate", result)
        _payload(tool_attributes, "junjo.agent.tool.result", result)
        operation_spans.append(
            _span(
                scenario,
                operation_index,
                service_name,
                trace_id,
                f"tool {call['name']}",
                agent_span_id,
                tool_attributes,
            )
        )
        operation_index += 1

    if calls and final_model and outcome == "completed":
        model_ordinal += 1
        response = {
            "v": 1,
            "type": "final_output",
            "output": {"answer": "done"},
            "usage": {"v": 1, "inputTokens": 10, "outputTokens": 4, "totalTokens": 14},
        }
        attributes: dict[str, Any] = {
            "junjo.telemetry.contract_version": 2,
            "junjo.agent.operation_type": "model_request",
            "junjo.agent.key": agent_key,
            "junjo.agent.runtime_id": run_id,
            "junjo.agent.operation.sequence": operation_index,
            "junjo.agent.model_request.ordinal": model_ordinal,
            "junjo.agent.model_request.state_revision": 0,
            "junjo.agent.model.driver_key": "scripted",
            "junjo.agent.model.provider": "junjo",
            "junjo.agent.model.name": "scripted-v1",
            "junjo.agent.model.response_candidate.available": True,
            "junjo.agent.model.response_type": "final_output",
            "junjo.agent.model.usage": _json(response["usage"]),
        }
        _payload(attributes, "junjo.agent.model.request", _model_request(run_id, model_ordinal, declared_tools))
        _payload(attributes, "junjo.agent.model.response_candidate", response)
        _payload(attributes, "junjo.agent.model.response", response)
        operation_spans.append(
            _span(scenario, operation_index, service_name, trace_id, f"model request {model_ordinal}", agent_span_id, attributes)
        )
        operation_index += 1
        validated_model_responses += 1

    requested_count = len(calls)
    admitted_count = min(observed_count, len(calls))
    started_count = admitted_count
    completed_count = admitted_count
    owner_attributes: dict[str, Any] = {
        "junjo.telemetry.contract_version": 2,
        "junjo.span_type": "agent",
        "junjo.executable_definition_id": definition_id,
        "junjo.executable_runtime_id": run_id,
        "junjo.executable_structural_id": structural_id,
        "junjo.agent.key": agent_key,
        "junjo.agent.name": agent_name,
        "junjo.agent.runtime_id": run_id,
        "junjo.agent.state.available": True,
        "junjo.agent.store.id": f"store-{_hex(scenario, 16)}",
        "junjo.agent.limit.model_requests": model_request_limit,
        "junjo.agent.limit.tool_calls": tool_call_limit,
        "junjo.agent.operation.count": len(operation_spans),
        "junjo.agent.model_request.count": model_ordinal,
        "junjo.agent.tool_call.requested_count": requested_count,
        "junjo.agent.tool_call.admitted_count": admitted_count,
        "junjo.agent.tool_call.started_count": started_count,
        "junjo.agent.tool_call.completed_count": completed_count,
        "junjo.agent.usage": _json(_usage(validated_model_responses)),
        "junjo.agent.outcome": outcome,
        "junjo.agent.termination_reason": reason,
        "junjo.store.revision.start": 0,
        "junjo.store.revision.end": 0,
        "junjo.store.transition.count": 0,
        "junjo.store.reconstructable": True,
    }
    _payload(owner_attributes, "junjo.agent.definition_snapshot", definition)
    _payload(owner_attributes, "junjo.agent.input", {"question": "fixture?"})
    _payload(owner_attributes, "junjo.agent.state.start", {"messages": []})
    _payload(owner_attributes, "junjo.agent.state.end", {"messages": []})
    if outcome == "completed":
        _payload(owner_attributes, "junjo.agent.output", {"answer": "done"})
    status_code = "0" if outcome in {"completed", "cancelled"} else "2"
    status_message = "" if status_code == "0" else reason
    spans.append(
        _span(
            scenario,
            0,
            service_name,
            trace_id,
            agent_name,
            None,
            owner_attributes,
            status_code=status_code,
            status_message=status_message,
        )
    )
    spans.extend(operation_spans)
    return {
        "contract_version": 2,
        "scenario": scenario,
        "trace_id": trace_id,
        "service_name": service_name,
        "spans": spans,
    }


def _agent_owner(case: dict[str, Any], index: int = 0) -> dict[str, Any]:
    owners = [
        span for span in case["spans"] if span["attributes_json"].get("junjo.span_type") == "agent"
    ]
    return owners[index]


def _operation_spans(case: dict[str, Any], owner: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    run_id = (owner or _agent_owner(case))["attributes_json"]["junjo.agent.runtime_id"]
    return [
        span
        for span in case["spans"]
        if span["attributes_json"].get("junjo.agent.runtime_id") == run_id
        and "junjo.agent.operation_type" in span["attributes_json"]
    ]


def _initial_agent_state(owner: dict[str, Any]) -> dict[str, Any]:
    """Mirror the private AgentState JSON projection owned by the SDK runtime."""
    attributes = owner["attributes_json"]
    normalized_input = json.loads(attributes["junjo.agent.input"])
    return {
        "input": normalized_input,
        "history": [],
        "transcript": [{"type": "agent_input", "input": copy.deepcopy(normalized_input)}],
        "model_iteration": 0,
        "model_request_count": 0,
        "tool_call_requested_count": 0,
        "tool_call_admitted_count": 0,
        "tool_call_started_count": 0,
        "tool_call_completed_count": 0,
        "usage": {"v": 1, "modelResponses": 0, "fields": {}},
        "admitted_tool_call_ids": [],
        "pending_tool_call_ids": [],
        "completed_tool_call_ids": [],
        "final_output_available": False,
        "final_output": None,
        "terminal_reason": None,
    }


def _add_usage(aggregate: dict[str, Any], usage: dict[str, Any] | None) -> dict[str, Any]:
    result = copy.deepcopy(aggregate)
    result["modelResponses"] += 1
    if usage is None:
        return result
    for field in (
        "inputTokens",
        "outputTokens",
        "cachedInputTokens",
        "reasoningTokens",
        "totalTokens",
    ):
        if field not in usage:
            continue
        current = result["fields"].setdefault(field, {"sum": 0, "observations": 0})
        current["sum"] += usage[field]
        current["observations"] += 1
    return result


def _apply_agent_state_evidence(case: dict[str, Any]) -> None:
    """Derive canonical Store evidence from the accepted Agent action grammar.

    Patch bodies are deterministic valid RFC 6902 root replacements. The shared
    contract standardizes replay semantics, not one language's diff algorithm.
    """

    for owner in [
        span
        for span in case["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
        and span["attributes_json"].get("junjo.agent.state.available") is True
    ]:
        owner_attributes = owner["attributes_json"]
        store_id = owner_attributes["junjo.agent.store.id"]
        operations = sorted(
            _operation_spans(case, owner),
            key=lambda span: span["attributes_json"]["junjo.agent.operation.sequence"],
        )
        evidence_spans = [owner, *operations]
        for span in evidence_spans:
            span["events_json"] = [
                event
                for event in span["events_json"]
                if not (
                    event.get("name") == "set_state"
                    and event.get("attributes", {}).get("junjo.store.id") == store_id
                )
            ]

        state = _initial_agent_state(owner)
        state_start = copy.deepcopy(state)
        revision = 0
        transition_sequence = 0

        def transition(
            span: dict[str, Any],
            action: str,
            updates: dict[str, Any],
        ) -> None:
            nonlocal revision, state, transition_sequence
            before = copy.deepcopy(state)
            state = {**state, **copy.deepcopy(updates)}
            changed = state != before
            revision_before = revision
            if changed:
                revision += 1
            transition_sequence += 1
            patch = (
                [{"op": "replace", "path": "", "value": copy.deepcopy(state)}]
                if changed
                else []
            )
            event_attributes: dict[str, Any] = {
                "id": f"event-{_hex(f'{store_id}:{transition_sequence}', 12)}",
                "junjo.store.name": "AgentStore",
                "junjo.store.id": store_id,
                "junjo.store.action": action,
                "junjo.store.transition.sequence": transition_sequence,
                "junjo.store.revision.before": revision_before,
                "junjo.store.revision.after": revision,
            }
            _payload(event_attributes, "junjo.state_json_patch", patch)
            span["events_json"].append(
                {
                    "name": "set_state",
                    "timeUnixNano": str(1783944000000000000 + transition_sequence),
                    "attributes": event_attributes,
                    "droppedAttributesCount": 0,
                }
            )

        target_admitted = owner_attributes["junjo.agent.tool_call.admitted_count"]
        target_started = owner_attributes["junjo.agent.tool_call.started_count"]
        target_completed = owner_attributes["junjo.agent.tool_call.completed_count"]
        for operation in operations:
            attributes = operation["attributes_json"]
            operation_type = attributes["junjo.agent.operation_type"]
            if operation_type == "model_request":
                ordinal = attributes["junjo.agent.model_request.ordinal"]
                transition(
                    operation,
                    "record_model_start",
                    {"model_iteration": ordinal, "model_request_count": ordinal},
                )
                attributes["junjo.agent.model_request.state_revision"] = revision
                request = json.loads(attributes["junjo.agent.model.request"])
                request["messages"] = [*state["history"], *state["transcript"]]
                attributes["junjo.agent.model.request"] = _json(request)

                response_type = attributes.get("junjo.agent.model.response_type")
                if response_type not in {"final_output", "tool_calls"}:
                    continue
                response = json.loads(attributes["junjo.agent.model.response"])
                usage = response.get("usage")
                aggregate_usage = _add_usage(state["usage"], usage)
                transcript = list(state["transcript"])
                calls = response.get("calls", []) if response_type == "tool_calls" else []
                if response_type == "tool_calls":
                    assistant_message: dict[str, Any] = {
                        "type": "assistant_tool_calls",
                        "calls": copy.deepcopy(calls),
                    }
                    if response.get("assistantText") is not None:
                        assistant_message["assistantText"] = response["assistantText"]
                    transcript.append(assistant_message)
                transition(
                    operation,
                    "record_model_response",
                    {
                        "transcript": transcript,
                        "tool_call_requested_count": (
                            state["tool_call_requested_count"] + len(calls)
                        ),
                        "usage": aggregate_usage,
                    },
                )

                if response_type == "tool_calls" and state["tool_call_admitted_count"] < target_admitted:
                    admitted_count = min(
                        len(calls), target_admitted - state["tool_call_admitted_count"]
                    )
                    admitted_ids = [call["id"] for call in calls[:admitted_count]]
                    transition(
                        owner,
                        "admit_tool_batch",
                        {
                            "tool_call_admitted_count": (
                                state["tool_call_admitted_count"] + len(admitted_ids)
                            ),
                            "admitted_tool_call_ids": [
                                *state["admitted_tool_call_ids"],
                                *admitted_ids,
                            ],
                            "pending_tool_call_ids": [
                                *state["pending_tool_call_ids"],
                                *admitted_ids,
                            ],
                        },
                    )
                continue

            attributes["junjo.agent.tool.state_revision.before"] = revision
            if (
                "junjo.agent.tool.arguments.mode" in attributes
                and state["tool_call_started_count"] < target_started
            ):
                transition(
                    operation,
                    "record_tool_started",
                    {"tool_call_started_count": state["tool_call_started_count"] + 1},
                )
            if (
                "junjo.agent.tool.result.mode" in attributes
                and state["tool_call_completed_count"] < target_completed
            ):
                call_id = attributes["junjo.agent.tool_call.id"]
                result = json.loads(attributes["junjo.agent.tool.result"])
                pending = list(state["pending_tool_call_ids"])
                if call_id in pending:
                    pending.remove(call_id)
                transition(
                    operation,
                    "record_tool_result",
                    {
                        "transcript": [
                            *state["transcript"],
                            {
                                "type": "tool_result",
                                "callId": call_id,
                                "toolName": attributes["junjo.agent.tool.name"],
                                "result": copy.deepcopy(result),
                            },
                        ],
                        "pending_tool_call_ids": pending,
                        "completed_tool_call_ids": [
                            *state["completed_tool_call_ids"],
                            call_id,
                        ],
                        "tool_call_completed_count": (
                            state["tool_call_completed_count"] + 1
                        ),
                    },
                )
                attributes["junjo.agent.tool.state_revision.after"] = revision
            else:
                attributes.pop("junjo.agent.tool.state_revision.after", None)

        if owner_attributes["junjo.agent.outcome"] == "completed":
            output = json.loads(owner_attributes["junjo.agent.output"])
            transition(
                owner,
                "commit_success",
                {
                    "transcript": [
                        *state["transcript"],
                        {"type": "assistant_output", "output": copy.deepcopy(output)},
                    ],
                    "final_output_available": True,
                    "final_output": output,
                    "terminal_reason": "final_output",
                },
            )
        else:
            transition(
                owner,
                "set_terminal_reason",
                {"terminal_reason": owner_attributes["junjo.agent.termination_reason"]},
            )
        owner_attributes["junjo.agent.model_request.count"] = state["model_request_count"]
        owner_attributes["junjo.agent.tool_call.requested_count"] = state[
            "tool_call_requested_count"
        ]
        owner_attributes["junjo.agent.tool_call.admitted_count"] = state[
            "tool_call_admitted_count"
        ]
        owner_attributes["junjo.agent.tool_call.started_count"] = state[
            "tool_call_started_count"
        ]
        owner_attributes["junjo.agent.tool_call.completed_count"] = state[
            "tool_call_completed_count"
        ]
        owner_attributes["junjo.agent.usage"] = _json(state["usage"])
        owner_attributes["junjo.store.revision.start"] = 0
        owner_attributes["junjo.store.revision.end"] = revision
        owner_attributes["junjo.store.transition.count"] = transition_sequence
        owner_attributes["junjo.store.reconstructable"] = True
        _payload(owner_attributes, "junjo.agent.state.start", state_start)
        _payload(owner_attributes, "junjo.agent.state.end", state)
        if case["scenario"] == "terminal_commit_internal_error_partial":
            owner_attributes["junjo.store.reconstructable"] = False


def _set_failure(
    span: dict[str, Any], error_type: str, message: str, time_ns: int = 1783944000000000000
) -> None:
    span["status_code"] = "2"
    span["status_message"] = message
    span["attributes_json"]["error.type"] = error_type
    runtime_messages = {
        "AgentAdmissionError": "Junjo could not prepare the validated Agent invocation for admission.",
        "AgentHistoryValidationError": "Agent history is not a sequence of complete normalized exchanges.",
        "AgentInputValidationError": "Agent input failed declared validation.",
        "AgentModelError": "ModelDriver failed while producing a normalized response.",
        "AgentModelResponseError": "ModelDriver returned an invalid normalized response.",
        "AgentOutputValidationError": "Final Agent output failed declared validation.",
        "AgentToolError": "Tool 'lookup' service failed.",
        "AgentToolInputValidationError": "Arguments for Tool 'lookup' failed declared validation.",
        "AgentToolOutputValidationError": "Tool 'lookup' output failed declared validation.",
        "AgentUnknownToolError": "Model requested unknown Tool 'missing'.",
    }
    if error_type == "AgentLimitExceededError":
        runtime_message = (
            "Agent Tool-call limit rejected the complete requested batch."
            if message == "tool_calls"
            else "Agent model-request limit was exhausted before another request could start."
        )
    elif error_type == "AgentInternalError":
        runtime_message = (
            "Unexpected error while committing the selected Agent outcome."
            if "terminal" in message
            else "Unexpected error inside the admitted Agent runtime."
        )
    else:
        runtime_message = runtime_messages.get(error_type, message)
    exception_type = (
        f"junjo.agent.errors.{error_type}"
        if error_type.startswith("Agent")
        else error_type
    )
    span["events_json"].append(
        _exception_event(exception_type, runtime_message, time_ns)
    )


def _set_cancelled(span: dict[str, Any], reason: str = "fixture cancellation") -> None:
    span["attributes_json"]["junjo.cancelled"] = True
    span["attributes_json"]["junjo.cancelled_reason"] = reason


def _workflow_fragment(case: dict[str, Any], parent_span_id: str, *, failed: bool = False) -> list[dict[str, Any]]:
    scenario = case["scenario"]
    trace_id = case["trace_id"]
    service_name = case["service_name"]
    workflow_span_id = _hex(f"{scenario}:span:100", 16)
    graph_id = f"graph-{_hex(scenario, 16)}"
    owner_attributes = _agent_owner(case)["attributes_json"]
    node_id = _hex(f"{scenario}:span:101", 16)
    graph = {
        "v": 2,
        "graphStructuralId": graph_id,
        "nodes": [
            {
                "nodeRuntimeId": f"node-{_hex(scenario, 10)}",
                "nodeStructuralId": f"node-struct-{_hex(scenario, 10)}",
                "nodeType": "NestedNode",
                "nodeLabel": "nested node",
            }
        ],
        "edges": [],
    }
    workflow_attributes: dict[str, Any] = {
        "junjo.telemetry.contract_version": 2,
        "junjo.span_type": "workflow",
        "junjo.executable_definition_id": f"workflow-definition-{_hex(scenario, 10)}",
        "junjo.executable_runtime_id": f"workflow-run-{_hex(scenario, 10)}",
        "junjo.executable_structural_id": graph_id,
        "junjo.enclosing_graph_structural_id": graph_id,
        "junjo.parent_executable_definition_id": owner_attributes[
            "junjo.executable_definition_id"
        ],
        "junjo.parent_executable_runtime_id": owner_attributes[
            "junjo.executable_runtime_id"
        ],
        "junjo.parent_executable_structural_id": owner_attributes[
            "junjo.executable_structural_id"
        ],
        "junjo.parent_executable_type": "agent",
        "junjo.workflow.execution_graph_snapshot": _json(graph),
        "junjo.workflow.store.id": f"workflow-store-{_hex(scenario, 10)}",
        "junjo.store.revision.start": 0,
        "junjo.store.revision.end": 0,
        "junjo.store.transition.count": 0,
        "junjo.store.reconstructable": True,
        "junjo.workflow.node.count": (
            0 if failed or scenario == "cancelled_workflow_tool" else 1
        ),
    }
    _payload(workflow_attributes, "junjo.workflow.state.start", {"value": "result-1"})
    _payload(workflow_attributes, "junjo.workflow.state.end", {"value": "result-1"})
    workflow = _span(
        scenario,
        100,
        service_name,
        trace_id,
        "nested workflow",
        parent_span_id,
        workflow_attributes,
        status_code="2" if failed else "0",
        status_message="nested failure" if failed else "",
    )
    node_attributes = {
        "junjo.telemetry.contract_version": 2,
        "junjo.span_type": "node",
        "junjo.executable_definition_id": f"node-definition-{_hex(scenario, 10)}",
        "junjo.executable_runtime_id": f"node-run-{_hex(scenario, 10)}",
        "junjo.executable_structural_id": f"node-struct-{_hex(scenario, 10)}",
        "junjo.enclosing_graph_structural_id": graph_id,
        "junjo.parent_executable_definition_id": workflow_attributes[
            "junjo.executable_definition_id"
        ],
        "junjo.parent_executable_runtime_id": workflow_attributes["junjo.executable_runtime_id"],
        "junjo.parent_executable_structural_id": graph_id,
    }
    node = _span(
        scenario,
        101,
        service_name,
        trace_id,
        "nested node",
        workflow_span_id,
        node_attributes,
        status_code="2" if failed else "0",
        status_message="nested failure" if failed else "",
    )
    if failed:
        _set_failure(workflow, "RuntimeError", "nested failure")
        _set_failure(node, "RuntimeError", "nested failure")
    _require_span_ids = (workflow_span_id, node_id)
    assert workflow["span_id"] == _require_span_ids[0] and node["span_id"] == _require_span_ids[1]
    return [workflow, node]


def _wrap_agent_in_workflow(case: dict[str, Any]) -> None:
    owner = _agent_owner(case)
    scenario = case["scenario"]
    trace_id = case["trace_id"]
    service_name = case["service_name"]
    workflow_id = _hex(f"{scenario}:span:200", 16)
    node_id = _hex(f"{scenario}:span:201", 16)
    graph_id = f"graph-{_hex(scenario, 16)}"
    workflow_attributes = {
        "junjo.telemetry.contract_version": 2,
        "junjo.span_type": "workflow",
        "junjo.executable_definition_id": f"workflow-definition-{_hex(scenario, 10)}",
        "junjo.executable_runtime_id": f"workflow-run-{_hex(scenario, 10)}",
        "junjo.executable_structural_id": graph_id,
        "junjo.enclosing_graph_structural_id": graph_id,
        "junjo.workflow.execution_graph_snapshot": _json(
            {
                "v": 2,
                "graphStructuralId": graph_id,
                "nodes": [
                    {
                        "nodeRuntimeId": f"node-run-{_hex(scenario, 10)}",
                        "nodeStructuralId": f"node-struct-{_hex(scenario, 10)}",
                        "nodeType": "AgentNode",
                        "nodeLabel": "agent node",
                    }
                ],
                "edges": [],
            }
        ),
        "junjo.workflow.store.id": f"workflow-store-{_hex(scenario, 10)}",
        "junjo.store.revision.start": 0,
        "junjo.store.revision.end": 0,
        "junjo.store.transition.count": 0,
        "junjo.store.reconstructable": True,
        "junjo.workflow.node.count": (
            1
            if _agent_owner(case)["attributes_json"]["junjo.agent.outcome"]
            == "completed"
            else 0
        ),
    }
    outer_state = {"question": "fixture?", "answer": None}
    _payload(workflow_attributes, "junjo.workflow.state.start", outer_state)
    _payload(workflow_attributes, "junjo.workflow.state.end", outer_state)
    workflow = _span(scenario, 200, service_name, trace_id, "outer workflow", None, workflow_attributes)
    node_attributes = {
        "junjo.telemetry.contract_version": 2,
        "junjo.span_type": "node",
        "junjo.executable_definition_id": f"node-definition-{_hex(scenario, 10)}",
        "junjo.executable_runtime_id": f"node-run-{_hex(scenario, 10)}",
        "junjo.executable_structural_id": f"node-struct-{_hex(scenario, 10)}",
        "junjo.enclosing_graph_structural_id": graph_id,
        "junjo.parent_executable_definition_id": workflow_attributes[
            "junjo.executable_definition_id"
        ],
        "junjo.parent_executable_runtime_id": workflow_attributes["junjo.executable_runtime_id"],
        "junjo.parent_executable_structural_id": graph_id,
    }
    node = _span(scenario, 201, service_name, trace_id, "agent node", workflow_id, node_attributes)
    owner["parent_span_id"] = node_id
    owner_attributes = owner["attributes_json"]
    owner_attributes.update(
        {
            "junjo.parent_executable_definition_id": node_attributes[
                "junjo.executable_definition_id"
            ],
            "junjo.parent_executable_runtime_id": node_attributes["junjo.executable_runtime_id"],
            "junjo.parent_executable_structural_id": node_attributes[
                "junjo.executable_structural_id"
            ],
            "junjo.parent_executable_type": "node",
        }
    )
    if owner_attributes["junjo.agent.outcome"] == "failed":
        error_type = owner_attributes["error.type"]
        _set_failure(workflow, error_type, owner_attributes["junjo.agent.termination_reason"])
        _set_failure(node, error_type, owner_attributes["junjo.agent.termination_reason"])
    elif owner_attributes["junjo.agent.outcome"] == "cancelled":
        _set_cancelled(workflow)
        _set_cancelled(node)
    case["spans"] = [workflow, node, *case["spans"]]


def _configure_case(scenario: str) -> dict[str, Any]:
    if scenario == "standalone_agent_under_non_junjo_span":
        case = _base_agent_case(scenario)
        owner = _agent_owner(case)
        ambient = _span(
            scenario,
            900,
            case["service_name"],
            case["trace_id"],
            "POST /chat",
            None,
            {"http.request.method": "POST", "http.route": "/chat"},
        )
        ambient["kind"] = "SERVER"
        ambient["start_time"] = "2026-07-13T11:59:59.000000+00:00"
        ambient["end_time"] = "2026-07-13T12:00:01.000000+00:00"
        owner["parent_span_id"] = ambient["span_id"]
        case["spans"].insert(0, ambient)
        return case
    if scenario == "ordered_multiple_tools":
        return _base_agent_case(scenario, requested_tools=("lookup", "search"))
    if scenario in {"multi_tool_first_failure", "multi_tool_first_cancellation"}:
        cancelled = scenario.endswith("cancellation")
        case = _base_agent_case(
            scenario,
            requested_tools=("lookup", "search"),
            observed_tools=1,
            final_model=False,
            outcome="cancelled" if cancelled else "failed",
            reason="cancelled" if cancelled else "tool_error",
        )
        owner = _agent_owner(case)
        tool = next(
            span
            for span in _operation_spans(case)
            if span["attributes_json"].get("junjo.agent.operation_type") == "tool"
        )
        owner_attributes = owner["attributes_json"]
        owner_attributes["junjo.agent.tool_call.admitted_count"] = 2
        owner_attributes["junjo.agent.tool_call.completed_count"] = 0
        tool_attributes = tool["attributes_json"]
        for root in (
            "junjo.agent.tool.result_candidate",
            "junjo.agent.tool.result",
        ):
            for key in list(tool_attributes):
                if key == root or key.startswith(f"{root}."):
                    tool_attributes.pop(key)
        tool_attributes["junjo.agent.tool.result_candidate.available"] = False
        tool_attributes["junjo.agent.tool.result_candidate.unavailable_reason"] = (
            "cancelled" if cancelled else "service_failed"
        )
        tool_attributes.pop("junjo.agent.tool.state_revision.after", None)
        if cancelled:
            _set_cancelled(tool)
            _set_cancelled(owner)
        else:
            _set_failure(tool, "AgentToolError", "first Tool failed")
            _set_failure(owner, "AgentToolError", "first Tool failed")
        return case
    if scenario in {"tool_invokes_nested_workflow", "nested_workflow_failure", "cancelled_workflow_tool"}:
        outcome = "completed"
        reason = "final_output"
        if scenario == "nested_workflow_failure":
            outcome, reason = "failed", "tool_error"
        elif scenario == "cancelled_workflow_tool":
            outcome, reason = "cancelled", "cancelled"
        case = _base_agent_case(
            scenario,
            requested_tools=("lookup",),
            final_model=outcome == "completed",
            outcome=outcome,
            reason=reason,
        )
        tool_span = next(
            span
            for span in _operation_spans(case)
            if span["attributes_json"].get("junjo.agent.operation_type") == "tool"
        )
        if outcome == "failed":
            _set_failure(tool_span, "AgentToolError", "nested failure")
            owner = _agent_owner(case)
            _set_failure(owner, "AgentToolError", "nested failure")
            for root in (
                "junjo.agent.tool.result_candidate",
                "junjo.agent.tool.result",
            ):
                for key in list(tool_span["attributes_json"]):
                    if key == root or key.startswith(f"{root}."):
                        tool_span["attributes_json"].pop(key)
            tool_span["attributes_json"]["junjo.agent.tool.result_candidate.available"] = False
            tool_span["attributes_json"][
                "junjo.agent.tool.result_candidate.unavailable_reason"
            ] = "service_failed"
            tool_span["attributes_json"].pop(
                "junjo.agent.tool.state_revision.after", None
            )
            owner["attributes_json"]["junjo.agent.tool_call.completed_count"] = 0
        elif outcome == "cancelled":
            _set_cancelled(tool_span)
            owner = _agent_owner(case)
            _set_cancelled(owner)
            for root in (
                "junjo.agent.tool.result_candidate",
                "junjo.agent.tool.result",
            ):
                for key in list(tool_span["attributes_json"]):
                    if key == root or key.startswith(f"{root}."):
                        tool_span["attributes_json"].pop(key)
            tool_span["attributes_json"]["junjo.agent.tool.result_candidate.available"] = False
            tool_span["attributes_json"][
                "junjo.agent.tool.result_candidate.unavailable_reason"
            ] = "cancelled"
            tool_span["attributes_json"].pop(
                "junjo.agent.tool.state_revision.after", None
            )
            owner["attributes_json"]["junjo.agent.tool_call.completed_count"] = 0
        fragment = _workflow_fragment(case, tool_span["span_id"], failed=outcome == "failed")
        if outcome == "cancelled":
            for span in fragment:
                _set_cancelled(span)
        case["spans"].extend(fragment)
        if scenario == "tool_invokes_nested_workflow":
            for span in case["spans"]:
                attributes = span["attributes_json"]
                if "junjo.span_type" in attributes:
                    attributes["junjo.correlation.type"] = "ai_chat.turn"
                    attributes["junjo.correlation.id"] = "turn-fixture-001"
        return case
    if scenario in {
        "agent_inside_workflow_node",
        "agent_failure_inside_workflow_node",
        "agent_cancellation_inside_workflow_node",
    }:
        outcome, reason = "completed", "final_output"
        if "failure" in scenario:
            outcome, reason = "failed", "model_error"
        elif "cancellation" in scenario:
            outcome, reason = "cancelled", "cancelled"
        case = _base_agent_case(scenario, outcome=outcome, reason=reason)
        owner = _agent_owner(case)
        model = _operation_spans(case)[0]
        if outcome == "failed":
            _set_failure(owner, "AgentModelError", "model_error")
            _set_failure(model, "AgentModelError", "model_error")
            unavailable_reason = "not_returned"
        elif outcome == "cancelled":
            _set_cancelled(owner)
            _set_cancelled(model)
            unavailable_reason = "cancelled"
        else:
            unavailable_reason = None
        if unavailable_reason is not None:
            model_attributes = model["attributes_json"]
            for root in (
                "junjo.agent.model.response_candidate",
                "junjo.agent.model.response",
            ):
                for key in list(model_attributes):
                    if key == root or key.startswith(f"{root}."):
                        model_attributes.pop(key)
            model_attributes["junjo.agent.model.response_candidate.available"] = False
            model_attributes[
                "junjo.agent.model.response_candidate.unavailable_reason"
            ] = unavailable_reason
            model_attributes.pop("junjo.agent.model.response_type", None)
            model_attributes.pop("junjo.agent.model.usage", None)
            owner["attributes_json"]["junjo.agent.usage"] = _json(_usage(0))
        _wrap_agent_in_workflow(case)
        return case
    if scenario == "boundary_input_history_rejection":
        case = _base_agent_case(scenario, outcome="failed", reason="input_validation_error")
        case["spans"] = []
        for index, (boundary, reason) in enumerate(
            (("input", "input_validation_error"), ("history", "history_validation_error"))
        ):
            single = _base_agent_case(f"{scenario}-{boundary}", outcome="failed", reason=reason)
            owner = _agent_owner(single)
            owner["trace_id"] = case["trace_id"]
            owner["service_name"] = case["service_name"]
            owner["resource_attributes_json"] = _resource(case["service_name"])
            attrs = owner["attributes_json"]
            attrs["junjo.agent.state.available"] = False
            for key in list(attrs):
                if key.startswith("junjo.agent.store") or key.startswith("junjo.agent.state") or key.startswith("junjo.store") or key.startswith("junjo.agent.input") or key.startswith("junjo.agent.output"):
                    attrs.pop(key)
            attrs["junjo.agent.state.available"] = False
            attrs["junjo.agent.operation.count"] = 0
            attrs["junjo.agent.model_request.count"] = 0
            attrs["junjo.agent.usage"] = _json(_usage(0))
            attrs[f"junjo.agent.{boundary}_candidate.available"] = True
            candidate = (
                {"invalid": True}
                if boundary == "input"
                else [{"type": "agent_input", "input": {"invalid": True}}]
            )
            _payload(attrs, f"junjo.agent.{boundary}_candidate", candidate)
            _set_failure(
                owner,
                "AgentInputValidationError"
                if boundary == "input"
                else "AgentHistoryValidationError",
                reason,
            )
            case["spans"].append(owner)
        return case
    if scenario == "unknown_tool":
        case = _base_agent_case(
            scenario,
            requested_tools=("missing",),
            observed_tools=0,
            final_model=False,
            outcome="failed",
            reason="unknown_tool",
        )
        _set_failure(_agent_owner(case), "AgentUnknownToolError", "missing")
        return case
    if scenario == "malformed_tool_arguments":
        case = _base_agent_case(
            scenario,
            requested_tools=("lookup",),
            final_model=False,
            outcome="failed",
            reason="tool_input_validation_error",
        )
        tool = next(span for span in _operation_spans(case) if span["attributes_json"].get("junjo.agent.operation_type") == "tool")
        attrs = tool["attributes_json"]
        invalid_arguments = {"wrong": True}
        _payload(attrs, "junjo.agent.tool.requested_arguments", invalid_arguments)
        model = next(
            span
            for span in _operation_spans(case)
            if span["attributes_json"].get("junjo.agent.operation_type")
            == "model_request"
        )
        for root in (
            "junjo.agent.model.response_candidate",
            "junjo.agent.model.response",
        ):
            response = json.loads(model["attributes_json"][root])
            response["calls"][0]["arguments"] = invalid_arguments
            model["attributes_json"][root] = _json(response)
        for root in ("junjo.agent.tool.arguments", "junjo.agent.tool.result_candidate", "junjo.agent.tool.result"):
            for key in list(attrs):
                if key == root or key.startswith(f"{root}."):
                    attrs.pop(key)
        attrs["junjo.agent.tool.result_candidate.available"] = False
        attrs["junjo.agent.tool.result_candidate.unavailable_reason"] = "not_invoked"
        attrs.pop("junjo.agent.tool.state_revision.after", None)
        owner = _agent_owner(case)
        owner_attrs = owner["attributes_json"]
        owner_attrs["junjo.agent.tool_call.admitted_count"] = 0
        owner_attrs["junjo.agent.tool_call.started_count"] = 0
        owner_attrs["junjo.agent.tool_call.completed_count"] = 0
        _set_failure(tool, "AgentToolInputValidationError", "invalid arguments")
        _set_failure(owner, "AgentToolInputValidationError", "invalid arguments")
        return case
    if scenario in {"malformed_model_response", "nonserializable_model_response_candidate", "model_driver_failure"}:
        reason = "model_response_error" if "failure" not in scenario else "model_error"
        case = _base_agent_case(scenario, outcome="failed", reason=reason)
        model = _operation_spans(case)[0]
        attrs = model["attributes_json"]
        for root in ("junjo.agent.model.response",):
            for key in list(attrs):
                if key == root or key.startswith(f"{root}."):
                    attrs.pop(key)
        attrs.pop("junjo.agent.model.response_type", None)
        attrs.pop("junjo.agent.model.usage", None)
        if scenario == "nonserializable_model_response_candidate":
            for key in list(attrs):
                if key == "junjo.agent.model.response_candidate" or key.startswith("junjo.agent.model.response_candidate."):
                    attrs.pop(key)
            attrs["junjo.agent.model.response_candidate.available"] = False
            attrs["junjo.agent.model.response_candidate.unavailable_reason"] = "not_json_serializable"
        elif scenario == "model_driver_failure":
            for key in list(attrs):
                if key == "junjo.agent.model.response_candidate" or key.startswith("junjo.agent.model.response_candidate."):
                    attrs.pop(key)
            attrs["junjo.agent.model.response_candidate.available"] = False
            attrs["junjo.agent.model.response_candidate.unavailable_reason"] = "not_returned"
        else:
            _payload(attrs, "junjo.agent.model.response_candidate", {"invalid": "response"})
        owner = _agent_owner(case)
        owner["attributes_json"]["junjo.agent.usage"] = _json(_usage(0))
        error_type = (
            "AgentModelError"
            if scenario == "model_driver_failure"
            else "AgentModelResponseError"
        )
        _set_failure(model, error_type, reason)
        _set_failure(owner, error_type, reason)
        return case
    if scenario in {
        "tool_service_failure",
        "tool_output_validation_failure",
        "nonserializable_tool_result_candidate",
    }:
        reason = "tool_error" if scenario == "tool_service_failure" else "tool_output_validation_error"
        case = _base_agent_case(
            scenario,
            requested_tools=("lookup",),
            final_model=False,
            outcome="failed",
            reason=reason,
        )
        tool = next(span for span in _operation_spans(case) if span["attributes_json"].get("junjo.agent.operation_type") == "tool")
        attrs = tool["attributes_json"]
        for key in list(attrs):
            if key == "junjo.agent.tool.result" or key.startswith("junjo.agent.tool.result."):
                attrs.pop(key)
        if scenario == "tool_service_failure":
            for key in list(attrs):
                if key == "junjo.agent.tool.result_candidate" or key.startswith("junjo.agent.tool.result_candidate."):
                    attrs.pop(key)
            attrs["junjo.agent.tool.result_candidate.available"] = False
            attrs["junjo.agent.tool.result_candidate.unavailable_reason"] = "service_failed"
        elif scenario == "nonserializable_tool_result_candidate":
            for key in list(attrs):
                if key == "junjo.agent.tool.result_candidate" or key.startswith("junjo.agent.tool.result_candidate."):
                    attrs.pop(key)
            attrs["junjo.agent.tool.result_candidate.available"] = False
            attrs["junjo.agent.tool.result_candidate.unavailable_reason"] = "not_json_serializable"
        else:
            _payload(
                attrs,
                "junjo.agent.tool.result_candidate",
                {"wrong": True},
            )
        owner = _agent_owner(case)
        owner["attributes_json"]["junjo.agent.tool_call.completed_count"] = 0
        error_type = (
            "AgentToolError"
            if scenario == "tool_service_failure"
            else "AgentToolOutputValidationError"
        )
        _set_failure(tool, error_type, reason)
        _set_failure(owner, error_type, reason)
        return case
    if scenario == "final_output_validation_failure":
        case = _base_agent_case(scenario, outcome="failed", reason="output_validation_error")
        model = _operation_spans(case)[0]
        response = {
            "v": 1,
            "type": "final_output",
            "output": {"wrong": True},
            "usage": {"v": 1, "inputTokens": 10, "outputTokens": 4, "totalTokens": 14},
        }
        model["attributes_json"]["junjo.agent.model.response_candidate"] = _json(response)
        model["attributes_json"]["junjo.agent.model.response"] = _json(response)
        _set_failure(_agent_owner(case), "AgentOutputValidationError", "output_validation_error")
        return case
    if scenario == "over_budget_tool_batch":
        case = _base_agent_case(
            scenario,
            requested_tools=("lookup", "search"),
            observed_tools=0,
            final_model=False,
            outcome="failed",
            reason="limit_exceeded",
            tool_call_limit=1,
        )
        owner = _agent_owner(case)
        attrs = owner["attributes_json"]
        attrs["junjo.agent.limit.exceeded"] = "tool_calls"
        attrs["junjo.agent.limit.attempted_count"] = 2
        attrs["junjo.agent.limit.requested_batch_size"] = 2
        _set_failure(owner, "AgentLimitExceededError", "tool_calls")
        return case
    if scenario == "model_request_limit_exhaustion":
        case = _base_agent_case(
            scenario,
            requested_tools=("lookup",),
            final_model=False,
            outcome="failed",
            reason="limit_exceeded",
            model_request_limit=1,
        )
        owner = _agent_owner(case)
        attrs = owner["attributes_json"]
        attrs["junjo.agent.limit.exceeded"] = "model_requests"
        attrs["junjo.agent.limit.attempted_count"] = 2
        _set_failure(owner, "AgentLimitExceededError", "model_requests")
        return case
    if scenario in {"cancelled_model_request", "cancelled_tool_service"}:
        calls = ("lookup",) if scenario == "cancelled_tool_service" else ()
        case = _base_agent_case(
            scenario,
            requested_tools=calls,
            final_model=False,
            outcome="cancelled",
            reason="cancelled",
        )
        target = _operation_spans(case)[-1]
        _set_cancelled(target)
        _set_cancelled(_agent_owner(case))
        if scenario == "cancelled_tool_service":
            attrs = target["attributes_json"]
            for key in list(attrs):
                if key == "junjo.agent.tool.result_candidate" or key.startswith("junjo.agent.tool.result_candidate.") or key == "junjo.agent.tool.result" or key.startswith("junjo.agent.tool.result."):
                    attrs.pop(key)
            attrs["junjo.agent.tool.result_candidate.available"] = False
            attrs["junjo.agent.tool.result_candidate.unavailable_reason"] = "cancelled"
            owner_attrs = _agent_owner(case)["attributes_json"]
            owner_attrs["junjo.agent.tool_call.completed_count"] = 0
        else:
            attrs = target["attributes_json"]
            for key in list(attrs):
                if key == "junjo.agent.model.response_candidate" or key.startswith("junjo.agent.model.response_candidate.") or key == "junjo.agent.model.response" or key.startswith("junjo.agent.model.response."):
                    attrs.pop(key)
            attrs["junjo.agent.model.response_candidate.available"] = False
            attrs["junjo.agent.model.response_candidate.unavailable_reason"] = "cancelled"
            attrs.pop("junjo.agent.model.response_type", None)
            attrs.pop("junjo.agent.model.usage", None)
            _agent_owner(case)["attributes_json"]["junjo.agent.usage"] = _json(_usage(0))
        return case
    if scenario == "concurrent_run_isolation":
        first = _base_agent_case(f"{scenario}-a")
        second = _base_agent_case(f"{scenario}-b")
        case = first
        case["scenario"] = scenario
        case["service_name"] = f"svc-agent-{scenario.replace('_', '-')}"
        case["trace_id"] = _hex(f"{scenario}:trace", 32)
        for span in [*first["spans"], *second["spans"]]:
            span["trace_id"] = case["trace_id"]
            span["service_name"] = case["service_name"]
            span["resource_attributes_json"] = _resource(case["service_name"])
        case["spans"] = [*first["spans"], *second["spans"]]
        return case
    if scenario == "usage_absent_vs_zero":
        case = _base_agent_case(scenario, requested_tools=("lookup",))
        models = [span for span in _operation_spans(case) if span["attributes_json"].get("junjo.agent.operation_type") == "model_request"]
        first_attrs = models[0]["attributes_json"]
        zero_usage = {"v": 1, "inputTokens": 0}
        first_attrs["junjo.agent.model.usage"] = _json(zero_usage)
        for root in (
            "junjo.agent.model.response_candidate",
            "junjo.agent.model.response",
        ):
            value = json.loads(first_attrs[root])
            value["usage"] = zero_usage
            first_attrs[root] = _json(value)
        second_attrs = models[1]["attributes_json"]
        second_attrs.pop("junjo.agent.model.usage", None)
        for root in (
            "junjo.agent.model.response_candidate",
            "junjo.agent.model.response",
        ):
            value = json.loads(second_attrs[root])
            value.pop("usage", None)
            second_attrs[root] = _json(value)
        return case
    if scenario == "hook_failure_then_success":
        case = _base_agent_case(scenario)
        _agent_owner(case)["events_json"].append(
            {
                "name": "junjo.hook_error",
                "timeUnixNano": "1783944000000000000",
                "attributes": {
                    "junjo.hook.event": "agent_started",
                    "junjo.hook.callback": "fixture.bad_hook",
                    "junjo.hook.error.type": "RuntimeError",
                    "junjo.hook.error.message": "observer failed",
                    "exception.type": "RuntimeError",
                    "exception.message": "observer failed",
                },
                "droppedAttributesCount": 0,
            }
        )
        return case
    if scenario == "terminal_observer_cancellation":
        case = _base_agent_case(scenario)
        _agent_owner(case)["events_json"].append(
            {
                "name": "junjo.hook_delivery_cancelled",
                "timeUnixNano": "1783944000000000000",
                "attributes": {
                    "junjo.hook.event": "agent_completed",
                    "junjo.hook.callback": "fixture.slow_hook",
                    "junjo.hook.delivery.cancelled_reason": "caller cancelled delivery",
                },
                "droppedAttributesCount": 0,
            }
        )
        return case
    if scenario == "unexpected_internal_error":
        case = _base_agent_case(
            scenario,
            outcome="failed",
            reason="internal_error",
        )
        _set_failure(
            _agent_owner(case),
            "AgentInternalError",
            "unexpected admitted runtime failure",
        )
        return case
    if scenario == "admission_internal_error":
        case = _base_agent_case(
            scenario,
            outcome="failed",
            reason="internal_error",
        )
        owner = _agent_owner(case)
        case["spans"] = [owner]
        attributes = owner["attributes_json"]
        attributes["junjo.agent.state.available"] = False
        for key in list(attributes):
            if (
                key.startswith("junjo.agent.store")
                or key.startswith("junjo.agent.input")
                or key.startswith("junjo.agent.output")
                or key.startswith("junjo.agent.state.start")
                or key.startswith("junjo.agent.state.end")
                or key.startswith("junjo.store")
            ):
                attributes.pop(key)
        attributes["junjo.agent.operation.count"] = 0
        attributes["junjo.agent.model_request.count"] = 0
        attributes["junjo.agent.tool_call.requested_count"] = 0
        attributes["junjo.agent.tool_call.admitted_count"] = 0
        attributes["junjo.agent.tool_call.started_count"] = 0
        attributes["junjo.agent.tool_call.completed_count"] = 0
        attributes["junjo.agent.usage"] = _json(_usage(0))
        _set_failure(owner, "AgentAdmissionError", "admission setup failed")
        return case
    if scenario == "terminal_commit_internal_error_partial":
        case = _base_agent_case(
            scenario,
            outcome="failed",
            reason="internal_error",
        )
        _set_failure(
            _agent_owner(case),
            "AgentInternalError",
            "terminal Store commit failed",
        )
        _agent_owner(case)["events_json"].append(
            {
                "name": "junjo.agent.terminal_commit_failed",
                "timeUnixNano": "1783944000000000000",
                "attributes": {
                    "junjo.agent.superseded_outcome": "completed",
                    "error.type": "RuntimeError",
                },
                "droppedAttributesCount": 0,
            }
        )
        return case
    if scenario == "nested_agent_owner_isolation":
        case = _base_agent_case(scenario, requested_tools=("lookup",))
        tool = next(span for span in _operation_spans(case) if span["attributes_json"].get("junjo.agent.operation_type") == "tool")
        workflow = _workflow_fragment(case, tool["span_id"])
        case["spans"].extend(workflow)
        inner = _base_agent_case(f"{scenario}-inner")
        inner_owner = _agent_owner(inner)
        inner_owner["parent_span_id"] = workflow[1]["span_id"]
        inner_owner["attributes_json"].update(
            {
                "junjo.parent_executable_definition_id": workflow[1][
                    "attributes_json"
                ]["junjo.executable_definition_id"],
                "junjo.parent_executable_runtime_id": workflow[1]["attributes_json"][
                    "junjo.executable_runtime_id"
                ],
                "junjo.parent_executable_structural_id": workflow[1][
                    "attributes_json"
                ]["junjo.executable_structural_id"],
                "junjo.parent_executable_type": "node",
            }
        )
        for span in inner["spans"]:
            span["trace_id"] = case["trace_id"]
            span["service_name"] = case["service_name"]
            span["resource_attributes_json"] = _resource(case["service_name"])
        case["spans"].extend(inner["spans"])
        return case
    return _base_agent_case(scenario)


def _configure_consumer_case(scenario: str) -> dict[str, Any]:
    case = _base_agent_case(
        scenario,
        requested_tools=("lookup",) if scenario == "redacted_operation_payloads" else (),
    )
    _apply_agent_state_evidence(case)
    if scenario == "dropped_evidence_partial":
        owner = _agent_owner(case)
        owner["resource_dropped_attributes_count"] = 1
        owner["dropped_events_count"] = 2
        owner["events_json"].append(
            {
                "name": "diagnostic",
                "timeUnixNano": "1783944000000000000",
                "attributes": {},
                "droppedAttributesCount": 3,
            }
        )
        return case

    if scenario == "redacted_operation_payloads":
        for operation in _operation_spans(case):
            attributes = operation["attributes_json"]
            if attributes.get("junjo.agent.operation_type") == "model_request":
                for root, value in (
                    ("junjo.agent.model.request", {"request": "redacted"}),
                    (
                        "junjo.agent.model.response_candidate",
                        {"candidate": "redacted"},
                    ),
                    ("junjo.agent.model.response", {"response": "redacted"}),
                ):
                    attributes[root] = _json(value)
                    attributes[f"{root}.mode"] = "redacted"
                    attributes[f"{root}.policy"] = "fixture.redacted.v1"
                continue

            requested_root = "junjo.agent.tool.requested_arguments"
            attributes[requested_root] = _json({"arguments": "redacted"})
            attributes[f"{requested_root}.mode"] = "redacted"
            attributes[f"{requested_root}.policy"] = "fixture.redacted.v1"

            arguments_root = "junjo.agent.tool.arguments"
            attributes.pop(arguments_root, None)
            attributes[f"{arguments_root}.mode"] = "excluded"
            attributes[f"{arguments_root}.policy"] = "fixture.excluded.v1"

            candidate_root = "junjo.agent.tool.result_candidate"
            attributes.pop(candidate_root, None)
            attributes[f"{candidate_root}.mode"] = "reference"
            attributes[f"{candidate_root}.policy"] = "fixture.reference.v1"
            attributes[f"{candidate_root}.reference"] = "fixture://tool-candidate"

            result_root = "junjo.agent.tool.result"
            attributes[result_root] = _json({"result": "redacted"})
            attributes[f"{result_root}.mode"] = "redacted"
            attributes[f"{result_root}.policy"] = "fixture.redacted.v1"
        return case

    if scenario == "policy_unavailable_store":
        owner = _agent_owner(case)
        attributes = owner["attributes_json"]
        for root in ("junjo.agent.state.start", "junjo.agent.state.end"):
            attributes.pop(root, None)
            attributes[f"{root}.mode"] = "excluded"
            attributes[f"{root}.policy"] = "fixture.excluded.v1"
        for span in [owner, *_operation_spans(case, owner)]:
            for event in span["events_json"]:
                event_attributes = event.get("attributes", {})
                if (
                    event.get("name") == "set_state"
                    and event_attributes.get("junjo.store.id")
                    == attributes["junjo.agent.store.id"]
                ):
                    event_attributes.pop("junjo.state_json_patch", None)
                    event_attributes["junjo.state_json_patch.mode"] = "excluded"
                    event_attributes["junjo.state_json_patch.policy"] = (
                        "fixture.excluded.v1"
                    )
        attributes["junjo.store.reconstructable"] = False
        return case

    owner = _agent_owner(case)
    attributes = owner["attributes_json"]
    for root in (
        "junjo.agent.definition_snapshot",
        "junjo.agent.state.start",
        "junjo.agent.state.end",
    ):
        value = json.loads(attributes[root])
        attributes[root] = _json({"redacted": True, "shape": type(value).__name__})
        attributes[f"{root}.mode"] = "redacted"
        attributes[f"{root}.policy"] = "fixture.redacted.v1"
    for key in list(attributes):
        if key == "junjo.agent.input" or key.startswith("junjo.agent.input."):
            attributes.pop(key)
    attributes["junjo.agent.input.mode"] = "excluded"
    attributes["junjo.agent.input.policy"] = "fixture.excluded.v1"
    for key in list(attributes):
        if key == "junjo.agent.output" or key.startswith("junjo.agent.output."):
            attributes.pop(key)
    attributes["junjo.agent.output.mode"] = "reference"
    attributes["junjo.agent.output.policy"] = "fixture.reference.v1"
    attributes["junjo.agent.output.reference"] = "fixture://agent-output"
    for span in [owner, *_operation_spans(case, owner)]:
        for event in span["events_json"]:
            event_attributes = event.get("attributes", {})
            if (
                event.get("name") == "set_state"
                and event_attributes.get("junjo.store.id")
                == attributes["junjo.agent.store.id"]
            ):
                event_attributes["junjo.state_json_patch"] = "[]"
                event_attributes["junjo.state_json_patch.mode"] = "redacted"
                event_attributes["junjo.state_json_patch.policy"] = "fixture.redacted.v1"
    attributes["junjo.store.reconstructable"] = True
    return case


def _make_invalid_derivatives(valid_cases: dict[str, dict[str, Any]]) -> None:
    for path in INVALID_AGENT_ROOT.glob("*.json"):
        path.unlink()

    derivatives: list[tuple[str, str, dict[str, Any]]] = []

    def derived(source: str) -> dict[str, Any]:
        return copy.deepcopy(valid_cases[source])

    def store_events(case: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        owner = _agent_owner(case)
        store_id = owner["attributes_json"]["junjo.agent.store.id"]
        found: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for span in [owner, *_operation_spans(case, owner)]:
            for event in span["events_json"]:
                if (
                    event.get("name") == "set_state"
                    and event.get("attributes", {}).get("junjo.store.id") == store_id
                ):
                    found.append((span, event))
        return sorted(
            found,
            key=lambda item: item[1]["attributes"][
                "junjo.store.transition.sequence"
            ],
        )

    case = derived("ordered_multiple_tools")
    operations = _operation_spans(case)
    operations[1]["attributes_json"]["junjo.agent.operation.sequence"] = 1
    derivatives.append(("duplicate_operation_sequence", "operation_sequence_duplicate", case))

    case = derived("ordered_multiple_tools")
    _operation_spans(case)[-1]["attributes_json"]["junjo.agent.operation.sequence"] = 5
    _agent_owner(case)["attributes_json"]["junjo.agent.operation.count"] = 5
    derivatives.append(("gapped_operation_sequence", "operation_sequence_gap", case))

    case = derived("direct_typed_completion")
    _operation_spans(case)[0]["attributes_json"]["junjo.agent.operation.sequence"] = 2
    derivatives.append(("out_of_range_operation_sequence", "operation_sequence_out_of_range", case))

    case = derived("direct_typed_completion")
    trailing_span, trailing_event = store_events(case)[-1]
    trailing_span["events_json"].remove(trailing_event)
    derivatives.append(("missing_trailing_transition", "transition_sequence_missing_trailing", case))

    case = derived("direct_typed_completion")
    duplicate_span, duplicate_source = store_events(case)[0]
    duplicate_span["events_json"].append(copy.deepcopy(duplicate_source))
    _agent_owner(case)["attributes_json"]["junjo.store.transition.count"] += 1
    derivatives.append(("duplicate_transition_sequence", "transition_sequence_duplicate", case))

    case = derived("direct_typed_completion")
    _gap_span, gap_event = store_events(case)[-1]
    gap_event["attributes"]["junjo.store.transition.sequence"] += 1
    _agent_owner(case)["attributes_json"]["junjo.store.transition.count"] += 1
    derivatives.append(("gapped_transition_sequence", "transition_sequence_gap", case))

    case = derived("direct_typed_completion")
    store_events(case)[0][1]["attributes"]["junjo.store.revision.before"] = 1
    derivatives.append(("revision_discontinuity", "revision_discontinuity", case))

    case = derived("direct_typed_completion")
    _agent_owner(case)["attributes_json"]["junjo.store.revision.end"] = 1
    derivatives.append(("terminal_revision_mismatch", "terminal_revision_mismatch", case))

    case = derived("direct_typed_completion")
    event_attrs = store_events(case)[-1][1]["attributes"]
    event_attrs["junjo.state_json_patch"] = '[{"op":"add","path":"/unexpected","value":true}]'
    derivatives.append(("patch_replay_mismatch", "patch_replay_mismatch", case))

    case = derived("direct_typed_completion")
    _agent_owner(case)["attributes_json"].pop("junjo.agent.definition_snapshot.policy")
    derivatives.append(("required_slot_omission", "required_payload_slot_missing", case))

    case = derived("direct_typed_completion")
    attrs = _agent_owner(case)["attributes_json"]
    attrs["junjo.agent.input.mode"] = "excluded"
    derivatives.append(("invalid_payload_slot", "invalid_payload_slot", case))

    case = derived("direct_typed_completion")
    _agent_owner(case)["attributes_json"]["junjo.agent.tool_call.completed_count"] = 1
    derivatives.append(("count_inequality", "tool_count_inequality", case))

    case = derived("ordered_multiple_tools")
    _agent_owner(case)["attributes_json"]["junjo.agent.limit.tool_calls"] = 1
    derivatives.append(("limit_mismatch", "tool_limit_mismatch", case))

    case = derived("ordered_multiple_tools")
    models = [span for span in _operation_spans(case) if span["attributes_json"].get("junjo.agent.operation_type") == "model_request"]
    models[-1]["attributes_json"]["junjo.agent.model_request.ordinal"] = 3
    derivatives.append(("model_ordinal_noncontiguous", "model_ordinal_noncontiguous", case))

    case = derived("ordered_multiple_tools")
    tool = next(span for span in _operation_spans(case) if span["attributes_json"].get("junjo.agent.operation_type") == "tool")
    tool["attributes_json"]["junjo.agent.tool_call.id"] = "wrong-call"
    derivatives.append(("tool_call_identity_mismatch", "tool_call_identity_mismatch", case))

    case = derived("direct_typed_completion")
    attributes = _agent_owner(case)["attributes_json"]
    raw_definition = attributes["junjo.agent.definition_snapshot"]
    attributes["junjo.agent.definition_snapshot"] = (
        '{"agentKey":"shadowed",' + raw_definition[1:]
    )
    derivatives.append(
        ("duplicate_payload_object_name", "duplicate_json_object_name", case)
    )

    case = derived("direct_typed_completion")
    _agent_owner(case)["attributes_json"]["junjo.agent.input"] = (
        '{"question":9007199254740992}'
    )
    derivatives.append(("unsafe_payload_integer", "nonportable_json_value", case))

    case = derived("direct_typed_completion")
    _agent_owner(case)["attributes_json"]["junjo.agent.input"] = (
        '{"question":"\\ud800"}'
    )
    derivatives.append(("invalid_payload_unicode", "nonportable_json_value", case))

    case = derived("boundary_input_history_rejection")
    attributes = _agent_owner(case, 0)["attributes_json"]
    _payload(attributes, "junjo.agent.input", {"question": "validated"})
    derivatives.append(
        (
            "boundary_rejection_with_validated_input",
            "unexpected_boundary_input_evidence",
            case,
        )
    )

    case = derived("boundary_input_history_rejection")
    input_owner = _agent_owner(case, 0)["attributes_json"]
    history_owner = _agent_owner(case, 1)["attributes_json"]
    for key, value in history_owner.items():
        if key == "junjo.agent.history_candidate" or key.startswith(
            "junjo.agent.history_candidate."
        ):
            input_owner[key] = copy.deepcopy(value)
    derivatives.append(
        (
            "boundary_rejection_with_wrong_candidate",
            "unexpected_boundary_candidate_evidence",
            case,
        )
    )

    case = derived("direct_typed_completion")
    attributes = _agent_owner(case)["attributes_json"]
    attributes["junjo.agent.input_candidate.available"] = True
    _payload(attributes, "junjo.agent.input_candidate", {"question": "unexpected"})
    derivatives.append(
        (
            "non_boundary_with_candidate",
            "unexpected_boundary_candidate_evidence",
            case,
        )
    )

    case = derived("model_driver_failure")
    model_attributes = _operation_spans(case)[0]["attributes_json"]
    _payload(
        model_attributes,
        "junjo.agent.model.response_candidate",
        {"unexpected": True},
    )
    derivatives.append(
        ("unavailable_candidate_with_payload", "invalid_candidate_evidence", case)
    )

    case = derived("direct_typed_completion")
    model_attributes = _operation_spans(case)[0]["attributes_json"]
    model_attributes[
        "junjo.agent.model.response_candidate.unavailable_reason"
    ] = "not_returned"
    derivatives.append(
        ("available_candidate_with_reason", "invalid_candidate_evidence", case)
    )

    case = derived("direct_typed_completion")
    model_attributes = _operation_spans(case)[0]["attributes_json"]
    model_attributes.pop("junjo.agent.model.response_type")
    derivatives.append(
        (
            "model_response_without_type",
            "invalid_model_response_evidence",
            case,
        )
    )

    case = derived("direct_typed_completion")
    model_attributes = _operation_spans(case)[0]["attributes_json"]
    for key in list(model_attributes):
        if key == "junjo.agent.model.response" or key.startswith(
            "junjo.agent.model.response."
        ):
            model_attributes.pop(key)
    model_attributes.pop("junjo.agent.model.response_type")
    model_attributes.pop("junjo.agent.model.usage", None)
    derivatives.append(
        (
            "completed_model_without_response",
            "invalid_model_response_transport",
            case,
        )
    )

    case = derived("model_driver_failure")
    model_attributes = _operation_spans(case)[0]["attributes_json"]
    model_attributes["junjo.agent.model.usage"] = _json(
        {"v": 1, "inputTokens": 1}
    )
    derivatives.append(
        ("model_usage_without_response", "model_usage_without_response", case)
    )

    case = derived("malformed_tool_arguments")
    tool_attributes = next(
        span["attributes_json"]
        for span in _operation_spans(case)
        if span["attributes_json"].get("junjo.agent.operation_type") == "tool"
    )
    _payload(tool_attributes, "junjo.agent.tool.arguments", {"query": "invalid"})
    derivatives.append(
        (
            "malformed_tool_with_validated_arguments",
            "unexpected_tool_arguments_evidence",
            case,
        )
    )

    case = derived("malformed_tool_arguments")
    tool_attributes = next(
        span["attributes_json"]
        for span in _operation_spans(case)
        if span["attributes_json"].get("junjo.agent.operation_type") == "tool"
    )
    tool_attributes[
        "junjo.agent.tool.result_candidate.unavailable_reason"
    ] = "service_failed"
    derivatives.append(
        (
            "started_tool_without_arguments",
            "invalid_tool_started_evidence",
            case,
        )
    )

    case = derived("ordered_multiple_tools")
    tool_attributes = next(
        span["attributes_json"]
        for span in _operation_spans(case)
        if span["attributes_json"].get("junjo.agent.operation_type") == "tool"
    )
    tool_attributes.pop("junjo.agent.tool.state_revision.after")
    derivatives.append(
        (
            "tool_result_without_revision",
            "invalid_tool_result_commit_evidence",
            case,
        )
    )

    case = derived("tool_service_failure")
    failed_tool = next(
        span
        for span in _operation_spans(case)
        if span["attributes_json"].get("junjo.agent.operation_type") == "tool"
    )
    successful_case = derived("ordered_multiple_tools")
    successful_tool = next(
        span
        for span in _operation_spans(successful_case)
        if span["attributes_json"].get("junjo.agent.operation_type") == "tool"
    )
    successful_attributes = successful_tool["attributes_json"]
    failed_attributes = failed_tool["attributes_json"]
    failed_attributes["junjo.agent.tool.state_revision.after"] = successful_attributes[
        "junjo.agent.tool.state_revision.after"
    ]
    for key, value in successful_attributes.items():
        if key == "junjo.agent.tool.result" or key.startswith("junjo.agent.tool.result."):
            failed_attributes[key] = copy.deepcopy(value)
    derivatives.append(
        (
            "failed_tool_with_validated_result",
            "invalid_tool_result_transport",
            case,
        )
    )

    case = derived("over_budget_tool_batch")
    attributes = _agent_owner(case)["attributes_json"]
    _payload(attributes, "junjo.agent.output", {"unexpected": True})
    derivatives.append(("failed_agent_with_output", "unexpected_output_evidence", case))

    case = derived("direct_typed_completion")
    nested: Any = "leaf"
    for _ in range(130):
        nested = [nested]
    _agent_owner(case)["attributes_json"]["junjo.agent.input"] = _json(nested)
    derivatives.append(
        ("payload_nesting_too_deep", "payload_nesting_too_deep", case)
    )

    case = derived("direct_typed_completion")
    store_events(case)[0][1]["attributes"].pop("junjo.store.name")
    derivatives.append(("missing_store_name", "invalid_store_name", case))

    case = derived("direct_typed_completion")
    store_events(case)[0][1]["attributes"].pop("id")
    derivatives.append(
        ("missing_transition_event_id", "missing_transition_event_id", case)
    )

    case = derived("direct_typed_completion")
    store_events(case)[0][1]["attributes"]["junjo.store.name"] = "DifferentStore"
    derivatives.append(("inconsistent_store_name", "invalid_store_name", case))

    case = derived("direct_typed_completion")
    _agent_owner(case)["attributes_json"][
        "junjo.agent.termination_reason"
    ] = "output_validation_error"
    derivatives.append(
        ("owner_outcome_reason_mismatch", "terminal_outcome_reason_mismatch", case)
    )

    case = derived("direct_typed_completion")
    owner = _agent_owner(case)
    attributes = owner["attributes_json"]
    attributes["junjo.agent.outcome"] = "failed"
    attributes["junjo.agent.termination_reason"] = "input_validation_error"
    for key in list(attributes):
        if key == "junjo.agent.output" or key.startswith("junjo.agent.output."):
            attributes.pop(key)
    attributes["junjo.agent.input_candidate.available"] = True
    _payload(attributes, "junjo.agent.input_candidate", {"question": "rejected"})
    _set_failure(owner, "AgentInputValidationError", "invalid input")
    derivatives.append(
        ("boundary_reason_with_available_state", "invalid_unavailable_agent_state", case)
    )

    case = derived("over_budget_tool_batch")
    attributes = _agent_owner(case)["attributes_json"]
    attributes["junjo.agent.termination_reason"] = "tool_error"
    for key in (
        "junjo.agent.limit.exceeded",
        "junjo.agent.limit.attempted_count",
        "junjo.agent.limit.requested_batch_size",
    ):
        attributes.pop(key)
    derivatives.append(
        ("requested_above_limit_without_limit_termination", "invalid_limit_evidence", case)
    )

    case = derived("cancelled_tool_service")
    tool_attributes = next(
        span["attributes_json"]
        for span in _operation_spans(case)
        if span["attributes_json"].get("junjo.agent.operation_type") == "tool"
    )
    tool_attributes[
        "junjo.agent.tool.result_candidate.unavailable_reason"
    ] = "service_failed"
    derivatives.append(
        (
            "cancelled_tool_with_non_cancelled_candidate_reason",
            "invalid_candidate_transport_correspondence",
            case,
        )
    )

    case = derived("direct_typed_completion")
    owner = _agent_owner(case)
    model = next(
        span
        for span in _operation_spans(case)
        if span["attributes_json"].get("junjo.agent.operation_type") == "model_request"
    )
    response_event = next(
        event
        for event in model["events_json"]
        if event["attributes"].get("junjo.store.action") == "record_model_response"
    )
    model["events_json"].remove(response_event)
    unrelated = copy.deepcopy(model)
    unrelated["span_id"] = _hex("out-of-scope-store-event", 16)
    unrelated["parent_span_id"] = owner["span_id"]
    unrelated["name"] = "unrelated"
    unrelated["attributes_json"] = {"junjo.telemetry.contract_version": 2}
    unrelated["events_json"] = [response_event]
    case["spans"].append(unrelated)
    derivatives.append(
        ("out_of_scope_agent_store_event", "store_causal_owner_mismatch", case)
    )

    case = derived("direct_typed_completion")
    owner = _agent_owner(case)
    owner["end_time"] = "2026-07-13T11:59:59.000000+00:00"
    derivatives.append(("inverted_span_interval", "invalid_span_interval", case))

    for name, diagnostic, fixture in derivatives:
        fixture["scenario"] = name
        _write(
            INVALID_AGENT_ROOT / f"{name}.json",
            {"expected_diagnostic": diagnostic, "fixture": fixture},
        )


def _fingerprint_material(settings: dict[str, Any]) -> dict[str, Any]:
    material = _agent_material("fingerprint_agent", ("lookup",))
    material["model"]["settings"] = settings
    return material


def _schema_normalization_inputs() -> list[tuple[str, list[dict[str, Any]]]]:
    nested_first = {
        "title": "Root",
        "$defs": {
            "Outer": {
                "title": "Outer",
                "type": "object",
                "required": ["nested"],
                "properties": {"nested": {"$ref": "#/$defs/Inner"}},
            },
            "Inner": {
                "title": "Inner",
                "type": "object",
                "required": ["value"],
                "properties": {
                    "value": {"title": "Value annotation", "type": "string"}
                },
            },
            "Unreachable": {"type": "integer"},
        },
        "$ref": "#/$defs/Outer",
    }
    nested_second = {
        "$ref": "#/definitions/Container",
        "definitions": {
            "UnusedRenamed": {"type": "integer"},
            "Payload": {
                "properties": {
                    "value": {"type": "string", "title": "Different annotation"}
                },
                "required": ["value"],
                "type": "object",
                "title": "Renamed payload",
            },
            "Container": {
                "properties": {
                    "nested": {"$ref": "#/definitions/Payload"}
                },
                "required": ["nested"],
                "type": "object",
            },
        },
    }

    recursive_first = {
        "$defs": {
            "Node": {
                "type": "object",
                "required": ["value"],
                "properties": {
                    "value": {"type": "string"},
                    "children": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/Node"},
                    },
                },
            }
        },
        "$ref": "#/$defs/Node",
    }
    recursive_second = {
        "$ref": "#/definitions/Tree",
        "definitions": {
            "Tree": {
                "properties": {
                    "children": {
                        "items": {"$ref": "#/definitions/Tree"},
                        "type": "array",
                    },
                    "value": {"type": "string"},
                },
                "required": ["value"],
                "type": "object",
            }
        },
    }

    cat = {
        "type": "object",
        "required": ["title", "kind"],
        "properties": {
            "kind": {"type": "string", "const": "cat"},
            "title": {"title": "Application title annotation", "type": "string"},
        },
    }
    dog = {
        "type": "object",
        "required": ["kind", "title"],
        "properties": {
            "kind": {"type": "string", "const": "dog"},
            "title": {"type": "string"},
        },
    }
    discriminator_first = {
        "$defs": {"Dog": dog, "Cat": cat},
        "type": "object",
        "required": ["pet"],
        "properties": {
            "pet": {
                "discriminator": {
                    "propertyName": "kind",
                    "mapping": {
                        "dog": "#/$defs/Dog",
                        "cat": "#/$defs/Cat",
                    },
                },
                "oneOf": [
                    {"$ref": "#/$defs/Cat"},
                    {"$ref": "#/$defs/Dog"},
                ],
            }
        },
    }
    discriminator_second = {
        "properties": {
            "pet": {
                "oneOf": [
                    {"$ref": "#/definitions/RenamedCat"},
                    {"$ref": "#/definitions/RenamedDog"},
                ],
                "discriminator": {
                    "mapping": {
                        "cat": "#/definitions/RenamedCat",
                        "dog": "#/definitions/RenamedDog",
                    },
                    "propertyName": "kind",
                },
            }
        },
        "required": ["pet"],
        "type": "object",
        "definitions": {
            "RenamedCat": copy.deepcopy(cat),
            "RenamedDog": copy.deepcopy(dog),
        },
    }

    title_first = {
        "title": "Presentation-only root name",
        "type": "object",
        "required": ["title"],
        "properties": {
            "title": {"title": "Presentation-only field name", "type": "string"}
        },
    }
    title_second = {
        "properties": {"title": {"type": "string"}},
        "required": ["title"],
        "type": "object",
        "title": "Different presentation-only root name",
    }

    order_first = {
        "type": "object",
        "required": ["second", "first"],
        "properties": {
            "second": {"enum": ["beta", "alpha"]},
            "first": {"type": ["string", "null"]},
        },
        "dependentRequired": {
            "second": ["first", "third"],
            "first": ["second"],
        },
        "examples": [{"second": "beta"}, {"second": "alpha"}],
        "oneOf": [{"required": ["first"]}, {"required": ["second"]}],
    }
    order_second = {
        "oneOf": [{"required": ["first"]}, {"required": ["second"]}],
        "examples": [{"second": "beta"}, {"second": "alpha"}],
        "dependentRequired": {
            "first": ["second"],
            "second": ["third", "first"],
        },
        "properties": {
            "first": {"type": ["null", "string"]},
            "second": {"enum": ["alpha", "beta"]},
        },
        "required": ["first", "second"],
        "type": "object",
    }

    dictionary_first = {
        "type": "object",
        "additionalProperties": {"type": "integer"},
    }
    dictionary_second = {
        "additionalProperties": {"title": "Dictionary value", "type": "integer"},
        "type": "object",
    }

    return [
        ("renamed_nested_definitions", [nested_first, nested_second]),
        ("recursive_definitions", [recursive_first, recursive_second]),
        ("discriminator_mapping", [discriminator_first, discriminator_second]),
        ("application_property_named_title", [title_first, title_second]),
        ("object_insertion_and_set_order", [order_first, order_second]),
        ("open_dictionary_schema", [dictionary_first, dictionary_second]),
    ]


def _invalid_schema_normalization_inputs() -> list[tuple[str, dict[str, Any], str]]:
    return [
        (
            "duplicate_required_member",
            {"type": "object", "required": ["value", "value"]},
            "duplicate_set_member",
        ),
        (
            "duplicate_type_member",
            {"type": ["null", "string", "null"]},
            "duplicate_set_member",
        ),
        (
            "duplicate_enum_member",
            {"enum": [{"value": 1}, {"value": 1}]},
            "duplicate_set_member",
        ),
        (
            "duplicate_dependent_required_member",
            {
                "type": "object",
                "dependentRequired": {"source": ["target", "target"]},
            },
            "duplicate_set_member",
        ),
        (
            "null_additional_properties",
            {"type": "object", "additionalProperties": None},
            "invalid_schema_profile",
        ),
        (
            "numeric_additional_properties",
            {"type": "object", "additionalProperties": 0},
            "invalid_schema_profile",
        ),
        (
            "open_structured_object",
            {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "additionalProperties": True,
            },
            "invalid_schema_profile",
        ),
    ]


def _write_schema_normalization_vectors() -> dict[str, dict[str, Any]]:
    normalized_by_name: dict[str, dict[str, Any]] = {}
    vectors: list[dict[str, Any]] = []
    for name, inputs in _schema_normalization_inputs():
        normalized = normalize_generated_schema(inputs[0])
        if not all(normalize_generated_schema(value) == normalized for value in inputs[1:]):
            raise ValueError(f"schema normalization vector {name!r} is not equivalent")
        normalized_by_name[name] = normalized
        vectors.append({"name": name, "inputs": inputs, "normalized": normalized})
    _write(
        FINGERPRINT_ROOT / "schema-normalization-v1.json",
        {
            "v": 1,
            "profile": "junjo.generated-json-schema.v1",
            "vectors": vectors,
            "invalid": [
                {"name": name, "input": value, "expected_error": expected_error}
                for name, value, expected_error in _invalid_schema_normalization_inputs()
            ],
        },
    )
    return normalized_by_name


def _write_fingerprint_vectors() -> None:
    normalized_schemas = _write_schema_normalization_vectors()
    vectors: list[dict[str, Any]] = []
    materials = [
        ("plain", _fingerprint_material({})),
        ("safe_integer_boundaries", _fingerprint_material({"min": -9007199254740991, "max": 9007199254740991})),
        ("negative_zero", _fingerprint_material({"value": -0.0})),
        ("exponent", _fingerprint_material({"large": 1e30, "small": 1e-7})),
        ("unicode_composed", _fingerprint_material({"value": "é"})),
        ("unicode_decomposed", _fingerprint_material({"value": "é"})),
    ]
    for name, material in materials:
        canonical_bytes = canonical_json_dumps(material)
        canonical = canonical_bytes.decode("utf-8")
        vectors.append(
            {
                "name": name,
                "kind": "agent",
                "material": material,
                "canonical": canonical,
                "structural_id": f"agent_sha256:{hashlib.sha256(canonical_bytes).hexdigest()}",
            }
        )
    tool = _tool_material("lookup")
    canonical_bytes = canonical_json_dumps(tool)
    canonical = canonical_bytes.decode("utf-8")
    vectors.append(
        {
            "name": "tool_plain",
            "kind": "tool",
            "material": tool,
            "canonical": canonical,
            "structural_id": f"tool_sha256:{hashlib.sha256(canonical_bytes).hexdigest()}",
        }
    )

    schema_agent = _fingerprint_material({"profile": "normalized-schema"})
    schema_agent["inputSchema"] = normalized_schemas["renamed_nested_definitions"]
    schema_agent["outputSchema"] = normalized_schemas["recursive_definitions"]
    schema_agent["tools"][0]["inputSchema"] = normalized_schemas[
        "application_property_named_title"
    ]
    schema_agent["tools"][0]["outputSchema"] = normalized_schemas[
        "object_insertion_and_set_order"
    ]
    canonical_bytes = canonical_json_dumps(schema_agent)
    vectors.append(
        {
            "name": "agent_normalized_schema_profile",
            "kind": "agent",
            "material": schema_agent,
            "canonical": canonical_bytes.decode("utf-8"),
            "structural_id": (
                f"agent_sha256:{hashlib.sha256(canonical_bytes).hexdigest()}"
            ),
        }
    )

    pet_tool = {
        "v": 1,
        "name": "pet",
        "description": "Discriminated pet contract.",
        "inputSchema": normalized_schemas["discriminator_mapping"],
        "outputSchema": {
            "additionalProperties": False,
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "type": "object",
        },
    }
    canonical_bytes = canonical_json_dumps(pet_tool)
    vectors.append(
        {
            "name": "tool_normalized_schema_profile",
            "kind": "tool",
            "material": pet_tool,
            "canonical": canonical_bytes.decode("utf-8"),
            "structural_id": (
                f"tool_sha256:{hashlib.sha256(canonical_bytes).hexdigest()}"
            ),
        }
    )
    _write(FINGERPRINT_ROOT / "agent-structural-v1.json", {"v": 1, "vectors": vectors})


def _write_store_patch_vectors() -> None:
    _write(
        STORE_FIXTURE_ROOT / "rfc6902-replay.json",
        {
            "v": 1,
            "valid": [
                {
                    "name": "empty_patch_noop",
                    "start": {"unchanged": True},
                    "patch": [],
                    "end": {"unchanged": True},
                },
                {
                    "name": "escaped_pointer",
                    "start": {"a/b": {"~key": 1}},
                    "patch": [{"op": "replace", "path": "/a~1b/~0key", "value": 2}],
                    "end": {"a/b": {"~key": 2}},
                },
                {
                    "name": "array_move",
                    "start": {"items": ["a", "b", "c"]},
                    "patch": [{"op": "move", "from": "/items/0", "path": "/items/2"}],
                    "end": {"items": ["b", "c", "a"]},
                },
                {
                    "name": "copy_and_test",
                    "start": {"source": {"value": 1}},
                    "patch": [
                        {"op": "test", "path": "/source/value", "value": 1},
                        {"op": "copy", "from": "/source", "path": "/copy"},
                    ],
                    "end": {"source": {"value": 1}, "copy": {"value": 1}},
                },
                {
                    "name": "root_replace",
                    "start": {"old": True},
                    "patch": [{"op": "replace", "path": "", "value": [1, 2]}],
                    "end": [1, 2],
                },
            ],
            "invalid": [
                {
                    "name": "failed_test",
                    "start": {"value": 1},
                    "patch": [{"op": "test", "path": "/value", "value": 2}],
                    "expected_diagnostic": "patch_test_failed",
                },
                {
                    "name": "move_into_child",
                    "start": {"parent": {"child": 1}},
                    "patch": [{"op": "move", "from": "/parent", "path": "/parent/new"}],
                    "expected_diagnostic": "invalid_state_patch",
                },
            ],
        },
    )


def generate_agent_fixtures() -> None:
    for root in (AGENT_PRODUCER_ROOT, AGENT_CONSUMER_ROOT):
        for path in root.glob("*.json"):
            path.unlink()
    valid_cases: dict[str, dict[str, Any]] = {}
    for scenario in AGENT_PRODUCER_SCENARIOS:
        case = _configure_case(scenario)
        _apply_agent_state_evidence(case)
        valid_cases[scenario] = case
        _write(AGENT_PRODUCER_ROOT / f"{scenario}.json", case)
    for scenario in AGENT_CONSUMER_SCENARIOS:
        case = _configure_consumer_case(scenario)
        valid_cases[scenario] = case
        _write(AGENT_CONSUMER_ROOT / f"{scenario}.json", case)
    _make_invalid_derivatives(valid_cases)
    _write_fingerprint_vectors()
    _write_store_patch_vectors()


def main() -> None:
    migrate_workflow_fixtures()
    generate_agent_fixtures()


if __name__ == "__main__":
    main()
