#!/usr/bin/env python3
"""Validate Junjo's canonical telemetry fixtures without third-party packages."""

from __future__ import annotations

import json
import string
from pathlib import Path
from typing import Any

CONTRACT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = CONTRACT_ROOT / "fixtures" / "workflow"
SCHEMA_ROOT = CONTRACT_ROOT / "schemas"
REQUIRED_SCENARIOS = {
    "basic_workflow_success",
    "cancelled_executable",
    "failed_executable_with_error_type",
    "hook_failure_on_surrounding_span",
    "run_concurrent_success",
    "subflow_with_parent_store",
}


class ContractValidationError(ValueError):
    """Raised when a canonical telemetry artifact violates the active contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractValidationError(message)


def _is_lower_hex(value: object, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in string.hexdigits.lower() for character in value)
        and value == value.lower()
    )


def _validate_graph_snapshot(raw_snapshot: object, fixture_name: str) -> None:
    _require(isinstance(raw_snapshot, str), f"{fixture_name}: graph snapshot must be a JSON string")
    snapshot = json.loads(raw_snapshot)
    _require(snapshot.get("v") == 2, f"{fixture_name}: graph snapshot version must be 2")
    _require(bool(snapshot.get("graphStructuralId")), f"{fixture_name}: graphStructuralId is required")
    _require(isinstance(snapshot.get("nodes"), list), f"{fixture_name}: graph nodes must be a list")
    _require(isinstance(snapshot.get("edges"), list), f"{fixture_name}: graph edges must be a list")

    node_runtime_ids: set[str] = set()
    for node in snapshot["nodes"]:
        _require(isinstance(node, dict), f"{fixture_name}: each graph node must be an object")
        for key in ("nodeRuntimeId", "nodeStructuralId", "nodeType", "nodeLabel"):
            _require(bool(node.get(key)), f"{fixture_name}: graph node is missing {key}")
        runtime_id = node["nodeRuntimeId"]
        _require(runtime_id not in node_runtime_ids, f"{fixture_name}: duplicate graph node {runtime_id}")
        node_runtime_ids.add(runtime_id)

    edge_structural_ids: set[str] = set()
    for edge in snapshot["edges"]:
        _require(isinstance(edge, dict), f"{fixture_name}: each graph edge must be an object")
        for key in (
            "edgeStructuralId",
            "tailNodeRuntimeId",
            "tailNodeStructuralId",
            "headNodeRuntimeId",
            "headNodeStructuralId",
            "edgeScope",
        ):
            _require(bool(edge.get(key)), f"{fixture_name}: graph edge is missing {key}")
        edge_id = edge["edgeStructuralId"]
        _require(edge_id not in edge_structural_ids, f"{fixture_name}: duplicate graph edge {edge_id}")
        edge_structural_ids.add(edge_id)
        _require(edge["tailNodeRuntimeId"] in node_runtime_ids, f"{fixture_name}: edge tail is unknown")
        _require(edge["headNodeRuntimeId"] in node_runtime_ids, f"{fixture_name}: edge head is unknown")


def _validate_fixture(path: Path, contract_version: int) -> None:
    fixture: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    name = path.stem
    _require(fixture.get("contract_version") == contract_version, f"{name}: wrong contract_version")
    _require(fixture.get("scenario") == name, f"{name}: scenario must match file name")
    _require(_is_lower_hex(fixture.get("trace_id"), 32), f"{name}: invalid trace_id")
    _require(bool(fixture.get("service_name")), f"{name}: service_name is required")
    _require(isinstance(fixture.get("spans"), list) and fixture["spans"], f"{name}: spans are required")

    span_ids: set[str] = set()
    graph_snapshot_count = 0
    for span in fixture["spans"]:
        _require(isinstance(span, dict), f"{name}: each span must be an object")
        _require(span.get("trace_id") == fixture["trace_id"], f"{name}: span trace_id mismatch")
        _require(span.get("service_name") == fixture["service_name"], f"{name}: service_name mismatch")
        _require(_is_lower_hex(span.get("span_id"), 16), f"{name}: invalid span_id")
        _require(span["span_id"] not in span_ids, f"{name}: duplicate span_id {span['span_id']}")
        span_ids.add(span["span_id"])
        _require(isinstance(span.get("attributes_json"), dict), f"{name}: attributes_json must be an object")
        _require(isinstance(span.get("events_json"), list), f"{name}: events_json must be a list")
        _require(isinstance(span.get("links_json"), list), f"{name}: links_json must be a list")

        attributes = span["attributes_json"]
        _require(
            attributes.get("junjo.telemetry.contract_version") == contract_version,
            f"{name}: span {span['span_id']} has the wrong telemetry contract version",
        )
        snapshot = attributes.get("junjo.workflow.execution_graph_snapshot")
        if snapshot is not None:
            graph_snapshot_count += 1
            _validate_graph_snapshot(snapshot, name)

        for event in span["events_json"]:
            _require(isinstance(event, dict), f"{name}: each event must be an object")
            event_attributes = event.get("attributes", {})
            _require(isinstance(event_attributes, dict), f"{name}: event attributes must be an object")
            state_patch = event_attributes.get("junjo.state_json_patch")
            if state_patch is not None:
                parsed_patch = json.loads(state_patch)
                _require(isinstance(parsed_patch, (list, dict)), f"{name}: invalid state patch")

    _require(graph_snapshot_count >= 1, f"{name}: expected at least one execution graph snapshot")


def main() -> None:
    contract_version = int((CONTRACT_ROOT / "VERSION").read_text(encoding="utf-8").strip())
    _require(contract_version > 0, "contract VERSION must be positive")
    schemas: dict[str, dict[str, Any]] = {}
    for schema_path in sorted(SCHEMA_ROOT.glob("*.json")):
        schemas[schema_path.name] = json.loads(schema_path.read_text(encoding="utf-8"))

    fixture_schema_version = schemas["telemetry-fixture.schema.json"]["properties"][
        "contract_version"
    ]["const"]
    _require(fixture_schema_version == contract_version, "fixture schema version does not match VERSION")
    graph_schema_version = schemas["execution-graph-snapshot.v2.schema.json"]["properties"]["v"][
        "const"
    ]
    _require(graph_schema_version == 2, "execution graph schema filename and version disagree")

    fixture_paths = sorted(FIXTURE_ROOT.glob("*.json"))
    scenarios = {path.stem for path in fixture_paths}
    _require(scenarios == REQUIRED_SCENARIOS, "canonical Workflow scenario set is incomplete")
    for fixture_path in fixture_paths:
        _validate_fixture(fixture_path, contract_version)

    print(f"Telemetry contract {contract_version}: validated {len(fixture_paths)} Workflow fixtures.")


if __name__ == "__main__":
    main()
