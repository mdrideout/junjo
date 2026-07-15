"""Generic Store replay and malformed-evidence safety tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.features.store_diagnostics.reconstruction import (
    AGENT_STORE_BOUNDARY,
    WORKFLOW_STORE_BOUNDARY,
    reconstruct_store,
)

VECTOR_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "telemetry"
    / "fixtures"
    / "store"
    / "rfc6902-replay.json"
)
VECTORS = json.loads(VECTOR_PATH.read_text())


def _payload(attributes: dict[str, Any], root: str, value: Any) -> None:
    attributes[root] = json.dumps(value, separators=(",", ":"))
    attributes[f"{root}.mode"] = "full"
    attributes[f"{root}.policy"] = "junjo.full.v1"


def _store_evidence(
    start: Any,
    end: Any,
    patch: Any,
    *,
    sequence: Any = 1,
    revision_before: Any = 0,
    revision_after: Any = 1,
    event_id: Any = "event-1",
    action: Any = "test",
    store_name: Any = "AgentStore",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    owner: dict[str, Any] = {
        "junjo.agent.state.available": True,
        "junjo.agent.store.id": "store-1",
        "junjo.store.revision.start": 0,
        "junjo.store.revision.end": revision_after,
        "junjo.store.transition.count": 1,
        "junjo.store.reconstructable": True,
    }
    _payload(owner, "junjo.agent.state.start", start)
    _payload(owner, "junjo.agent.state.end", end)
    event_attributes: dict[str, Any] = {
        "id": event_id,
        "junjo.store.name": store_name,
        "junjo.store.id": "store-1",
        "junjo.store.action": action,
        "junjo.store.transition.sequence": sequence,
        "junjo.store.revision.before": revision_before,
        "junjo.store.revision.after": revision_after,
    }
    _payload(event_attributes, "junjo.state_json_patch", patch)
    span = {
        "span_id": "1111111111111111",
        "events_json": [{"name": "set_state", "attributes": event_attributes}],
    }
    return owner, [span]


@pytest.mark.parametrize("vector", VECTORS["valid"], ids=lambda vector: vector["name"])
def test_reconstructs_full_rfc6902_vectors(vector: dict[str, Any]) -> None:
    owner, spans = _store_evidence(vector["start"], vector["end"], vector["patch"])
    result = reconstruct_store(owner, spans, AGENT_STORE_BOUNDARY)
    assert result.detail.reconstructable is True
    assert result.detail.reconstruction_status == "verified"
    assert result.replay_verified is True
    assert result.detail.transitions[0].after == vector["end"]
    assert result.diagnostics == []


@pytest.mark.parametrize("vector", VECTORS["invalid"], ids=lambda vector: vector["name"])
def test_invalid_rfc6902_vectors_are_not_reconstructable(vector: dict[str, Any]) -> None:
    owner, spans = _store_evidence(vector["start"], vector["start"], vector["patch"])
    result = reconstruct_store(owner, spans, AGENT_STORE_BOUNDARY)
    assert result.detail.reconstructable is False
    assert result.detail.reconstruction_status == "failed"
    assert "patch_replay_mismatch" in {diagnostic.code for diagnostic in result.diagnostics}


def test_bool_owner_integer_is_rejected_without_crashing() -> None:
    owner, spans = _store_evidence({}, {}, [])
    owner["junjo.store.revision.start"] = True
    result = reconstruct_store(owner, spans, AGENT_STORE_BOUNDARY)
    assert result.detail.reconstructable is False
    assert "invalid_store_owner_fact" in {diagnostic.code for diagnostic in result.diagnostics}


def test_mixed_transition_sequences_have_total_order_and_partial_diagnostics() -> None:
    owner, spans = _store_evidence({}, {}, [], sequence="one", revision_after=0)
    second_owner, second_spans = _store_evidence({}, {}, [], sequence=2, revision_after=0)
    owner["junjo.store.transition.count"] = 2
    owner["junjo.store.revision.end"] = 0
    spans.extend(second_spans)
    result = reconstruct_store(owner, spans, AGENT_STORE_BOUNDARY)
    assert result.detail.reconstructable is False
    assert "transition_sequence_out_of_range" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


@pytest.mark.parametrize("missing", ["id", "action"])
def test_missing_event_identity_is_diagnosed_not_coerced(missing: str) -> None:
    kwargs = {"event_id": None} if missing == "id" else {"action": None}
    owner, spans = _store_evidence({}, {}, [], revision_after=0, **kwargs)
    result = reconstruct_store(owner, spans, AGENT_STORE_BOUNDARY)
    assert result.detail.transitions == []
    expected = "missing_transition_event_id" if missing == "id" else "missing_transition_action"
    assert expected in {diagnostic.code for diagnostic in result.diagnostics}


@pytest.mark.parametrize(
    "store_name",
    [None, {}, [], "\ud800"],
    ids=["missing", "object", "array", "lone-surrogate"],
)
def test_invalid_store_name_is_diagnosed_not_coerced(store_name: Any) -> None:
    owner, spans = _store_evidence(
        {},
        {},
        [],
        revision_after=0,
        store_name=store_name,
    )

    result = reconstruct_store(owner, spans, AGENT_STORE_BOUNDARY)

    assert result.detail.reconstructable is False
    assert result.replay_verified is False
    assert "invalid_store_name" in {diagnostic.code for diagnostic in result.diagnostics}


def test_one_store_id_cannot_change_names_between_transitions() -> None:
    final_state = {"a": 1, "b": 2}
    owner, spans = _store_evidence(
        {},
        final_state,
        [{"op": "add", "path": "/a", "value": 1}],
        store_name="AgentStore",
    )
    owner["junjo.store.revision.end"] = 2
    owner["junjo.store.transition.count"] = 2
    _, second_spans = _store_evidence(
        {"a": 1},
        final_state,
        [{"op": "add", "path": "/b", "value": 2}],
        sequence=2,
        revision_before=1,
        revision_after=2,
        event_id="event-2",
        store_name="RenamedStore",
    )
    spans.extend(second_spans)

    result = reconstruct_store(owner, spans, AGENT_STORE_BOUNDARY)

    assert result.detail.reconstructable is False
    assert result.replay_verified is False
    assert "invalid_store_name" in {diagnostic.code for diagnostic in result.diagnostics}


def test_one_store_name_across_distinct_actions_replays_successfully() -> None:
    final_state = {"a": 1, "b": 2}
    owner, spans = _store_evidence(
        {},
        final_state,
        [{"op": "add", "path": "/a", "value": 1}],
        action="first_action",
        store_name="StableStore",
    )
    owner["junjo.store.revision.end"] = 2
    owner["junjo.store.transition.count"] = 2
    _, second_spans = _store_evidence(
        {"a": 1},
        final_state,
        [{"op": "add", "path": "/b", "value": 2}],
        sequence=2,
        revision_before=1,
        revision_after=2,
        event_id="event-2",
        action="second_action",
        store_name="StableStore",
    )
    spans.extend(second_spans)

    result = reconstruct_store(owner, spans, AGENT_STORE_BOUNDARY)

    assert result.detail.reconstructable is True
    assert result.replay_verified is True
    assert [transition.action for transition in result.detail.transitions] == [
        "first_action",
        "second_action",
    ]
    assert result.diagnostics == []


@pytest.mark.parametrize("mode", ["excluded", "reference"])
def test_intentional_payload_policy_unavailability_is_not_corruption(mode: str) -> None:
    owner, spans = _store_evidence({}, {}, [], revision_after=0)
    owner["junjo.store.reconstructable"] = False
    for root in ("junjo.agent.state.start", "junjo.agent.state.end"):
        owner.pop(root)
        owner[f"{root}.mode"] = mode
        owner[f"{root}.policy"] = f"junjo.{mode}.v1"
        if mode == "reference":
            owner[f"{root}.reference"] = f"urn:test:{root}"
    attributes = spans[0]["events_json"][0]["attributes"]
    attributes.pop("junjo.state_json_patch")
    attributes["junjo.state_json_patch.mode"] = mode
    attributes["junjo.state_json_patch.policy"] = f"junjo.{mode}.v1"
    if mode == "reference":
        attributes["junjo.state_json_patch.reference"] = "urn:test:patch"

    result = reconstruct_store(owner, spans, AGENT_STORE_BOUNDARY)

    assert result.detail.reconstructable is False
    assert result.detail.reconstruction_status == "policy_unavailable"
    assert result.detail.reconstruction_reason == "payload_policy"
    assert result.replay_verified is False
    assert result.diagnostics == []


def test_conservative_producer_claim_does_not_override_verified_replay() -> None:
    owner, spans = _store_evidence({}, {"value": 1}, [{"op": "add", "path": "/value", "value": 1}])
    owner["junjo.store.reconstructable"] = False

    result = reconstruct_store(owner, spans, AGENT_STORE_BOUNDARY)

    assert result.detail.reconstructable_claimed is False
    assert result.detail.reconstructable is True
    assert result.detail.reconstruction_status == "verified"
    assert result.diagnostics == []


def test_producer_reconstructable_claim_requires_independent_verification() -> None:
    owner, spans = _store_evidence({}, {}, [], revision_after=0)
    for root in ("junjo.agent.state.start", "junjo.agent.state.end"):
        owner.pop(root)
        owner[f"{root}.mode"] = "excluded"
        owner[f"{root}.policy"] = "junjo.excluded.v1"
    attributes = spans[0]["events_json"][0]["attributes"]
    attributes.pop("junjo.state_json_patch")
    attributes["junjo.state_json_patch.mode"] = "excluded"
    attributes["junjo.state_json_patch.policy"] = "junjo.excluded.v1"

    result = reconstruct_store(owner, spans, AGENT_STORE_BOUNDARY)

    assert result.detail.reconstruction_status == "failed"
    assert result.detail.reconstruction_reason == "reconstructable_claim_mismatch"
    assert "reconstructable_claim_mismatch" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_state_unavailable_rejects_fabricated_store_evidence() -> None:
    owner = {
        "junjo.agent.state.available": False,
        "junjo.agent.runtime_id": "agent-run",
        "junjo.agent.store.id": "fabricated-store",
    }
    spans = [
        {
            "span_id": "1111111111111111",
            "attributes_json": {"junjo.agent.runtime_id": "agent-run"},
            "events_json": [
                {
                    "name": "set_state",
                    "attributes": {"junjo.store.id": "fabricated-store"},
                }
            ],
        }
    ]

    result = reconstruct_store(owner, spans, AGENT_STORE_BOUNDARY)

    assert result.detail.reconstruction_status == "not_applicable"
    assert result.detail.reconstruction_reason == "state_unavailable"
    assert "fabricated_boundary_store" in {diagnostic.code for diagnostic in result.diagnostics}


def test_state_unavailable_ignores_unrelated_workflow_store_events() -> None:
    owner = {
        "junjo.agent.state.available": False,
        "junjo.agent.runtime_id": "agent-run",
    }
    spans = [
        {
            "span_id": "1111111111111111",
            "attributes_json": {
                "junjo.span_type": "workflow",
                "junjo.executable_runtime_id": "workflow-run",
            },
            "events_json": [
                {
                    "name": "set_state",
                    "attributes": {"junjo.store.id": "workflow-store"},
                }
            ],
        }
    ]

    result = reconstruct_store(owner, spans, AGENT_STORE_BOUNDARY)

    assert result.detail.reconstruction_status == "not_applicable"
    assert result.detail.reconstruction_reason == "state_unavailable"
    assert result.diagnostics == []


def test_state_unavailable_rejects_owner_attributable_store_event_without_owner_facts() -> None:
    owner = {
        "junjo.agent.state.available": False,
        "junjo.agent.runtime_id": "agent-run",
    }
    spans = [
        {
            "span_id": "1111111111111111",
            "attributes_json": {"junjo.agent.runtime_id": "agent-run"},
            "events_json": [
                {
                    "name": "set_state",
                    "attributes": {"junjo.store.id": "fabricated-store"},
                }
            ],
        }
    ]

    result = reconstruct_store(owner, spans, AGENT_STORE_BOUNDARY)

    assert "fabricated_boundary_store" in {diagnostic.code for diagnostic in result.diagnostics}


@pytest.mark.parametrize(
    "boundary",
    [AGENT_STORE_BOUNDARY, WORKFLOW_STORE_BOUNDARY],
    ids=["agent", "workflow"],
)
def test_store_reconstruction_rejects_noncanonical_transition_carrier_identity(
    boundary,
) -> None:
    owner, spans = _store_evidence(
        {},
        {"value": 1},
        [{"op": "add", "path": "/value", "value": 1}],
    )
    if boundary is WORKFLOW_STORE_BOUNDARY:
        owner = {
            key.replace("junjo.agent.store.id", "junjo.workflow.store.id")
            .replace("junjo.agent.state.start", "junjo.workflow.state.start")
            .replace("junjo.agent.state.end", "junjo.workflow.state.end"): value
            for key, value in owner.items()
            if key != "junjo.agent.state.available"
        }
    spans[0]["span_id"] = "not-a-span-id"

    result = reconstruct_store(owner, spans, boundary)

    assert result.detail.reconstructable is False
    assert result.detail.reconstruction_status == "failed"
    assert result.detail.transitions == []
    assert "invalid_span_id" in {diagnostic.code for diagnostic in result.diagnostics}


def test_agent_and_workflow_boundaries_share_exact_replay_semantics() -> None:
    owner, spans = _store_evidence(
        {"value": 0},
        {"value": 1},
        [{"op": "replace", "path": "/value", "value": 1}],
    )
    agent = reconstruct_store(owner, spans, AGENT_STORE_BOUNDARY)

    workflow_owner = {
        key.replace("junjo.agent.store.id", "junjo.workflow.store.id")
        .replace("junjo.agent.state.start", "junjo.workflow.state.start")
        .replace("junjo.agent.state.end", "junjo.workflow.state.end"): value
        for key, value in owner.items()
        if key != "junjo.agent.state.available"
    }
    workflow = reconstruct_store(
        workflow_owner,
        spans,
        WORKFLOW_STORE_BOUNDARY,
    )

    assert workflow.detail == agent.detail
    assert workflow.diagnostics == agent.diagnostics == []
