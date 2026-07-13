"""Conformance checks between Python graph telemetry and the shared contract."""

from __future__ import annotations

import json
from pathlib import Path

from junjo import BaseState, BaseStore, Edge, Graph, Node
from junjo.telemetry.otel_schema import JUNJO_TELEMETRY_CONTRACT_VERSION

CONTRACT_ROOT = Path(__file__).resolve().parents[3] / "contracts" / "telemetry"


class ContractState(BaseState):
    """Minimal state used by the graph contract test."""


class ContractStore(BaseStore[ContractState]):
    """Minimal store used by the graph contract test."""


class ContractNode(Node[ContractStore]):
    """Minimal node used by the graph contract test."""

    async def service(self, store: ContractStore) -> None:
        """Perform no work; only the node's graph representation is exercised."""


def test_python_graph_snapshot_matches_shared_schema_version_and_shape() -> None:
    """Keep the emitted Python graph payload aligned with the canonical schema."""
    source = ContractNode()
    sink = ContractNode()
    graph = Graph(source=source, sinks=[sink], edges=[Edge(tail=source, head=sink)])

    snapshot = json.loads(graph.serialize_to_json_string())
    schema = json.loads(
        (CONTRACT_ROOT / "schemas" / "execution-graph-snapshot.v2.schema.json").read_text(
            encoding="utf-8"
        )
    )

    assert snapshot["v"] == schema["properties"]["v"]["const"]
    assert set(schema["required"]).issubset(snapshot)
    assert all(set(schema["$defs"]["node"]["required"]).issubset(node) for node in snapshot["nodes"])
    assert all(set(schema["$defs"]["edge"]["required"]).issubset(edge) for edge in snapshot["edges"])


def test_python_sdk_targets_the_active_telemetry_contract() -> None:
    """Make the current cross-system compatibility version explicit to the SDK."""
    active_contract_version = int((CONTRACT_ROOT / "VERSION").read_text(encoding="utf-8").strip())

    assert JUNJO_TELEMETRY_CONTRACT_VERSION == active_contract_version
