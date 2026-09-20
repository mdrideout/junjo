"""Shared physical events retain separate, independently verified execution views."""

import copy
import json
from pathlib import Path

from app.features.trace_evidence.assembler import assemble_trace_evidence, hydrate_store_view

FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "contracts/telemetry/fixtures/agent/producer/shared_application_store.json"
)


def projection():
    fixture = json.loads(FIXTURE.read_text())
    return fixture, assemble_trace_evidence(fixture["trace_id"], fixture["spans"])


def test_shared_store_views_are_independent_and_events_are_not_duplicated():
    _, evidence = projection()
    agent = next(
        item for item in evidence.executables_by_span_id.values() if item.executable_type == "agent"
    )
    workflow = next(
        item
        for item in evidence.executables_by_span_id.values()
        if item.executable_type == "workflow"
    )
    app = agent.stores["application"]
    child = workflow.stores["application"]
    assert app.store_id == child.store_id != agent.stores["runtime"].store_id
    assert (app.sequence_start, app.sequence_end, app.revision_start) == (2, 5, 1)
    assert (child.sequence_start, child.sequence_end, child.revision_start) == (3, 4, 2)
    assert len(evidence.stores_by_id[app.store_id].transitions) == 3
    assert [
        item.sequence for item in hydrate_store_view(child, evidence.stores_by_id).transitions
    ] == [4]
    assert app.reconstructable and child.reconstructable
    assert evidence.diagnostics == []


def test_missing_shared_writer_only_invalidates_views_that_need_its_event():
    fixture, _ = projection()
    for span in fixture["spans"]:
        span["events_json"] = [
            event
            for event in span["events_json"]
            if event["attributes"].get("id") != "event-shared-3"
        ]
    evidence = assemble_trace_evidence(fixture["trace_id"], fixture["spans"])
    agent = next(
        item for item in evidence.executables_by_span_id.values() if item.executable_type == "agent"
    )
    workflow = next(
        item
        for item in evidence.executables_by_span_id.values()
        if item.executable_type == "workflow"
    )
    assert not agent.stores["application"].reconstructable
    assert agent.stores["runtime"].reconstructable
    assert workflow.stores["application"].reconstructable
    assert all(
        item.before is None
        for item in hydrate_store_view(
            agent.stores["application"], evidence.stores_by_id
        ).transitions
    )
    assert any(item.issue.code == "transition_sequence_gap" for item in evidence.diagnostics)


def test_overlapping_views_on_same_store_keep_their_own_checkpoints():
    fixture, _ = projection()
    agent = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    original = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "workflow"
    )
    sibling = copy.deepcopy(original)
    sibling["span_id"] = "f" * 16
    attrs = sibling["attributes_json"]
    attrs["junjo.executable_runtime_id"] = "overlapping-workflow"
    for suffix in (
        "revision.start",
        "revision.end",
        "transition.start",
        "transition.end",
        "transition.count",
    ):
        attrs[f"junjo.store.{suffix}"] = agent["attributes_json"][
            f"junjo.agent.application_store.{suffix}"
        ]
    for suffix in ("start", "end"):
        attrs[f"junjo.workflow.state.{suffix}"] = agent["attributes_json"][
            f"junjo.agent.application_state.{suffix}"
        ]
    fixture["spans"].append(sibling)
    evidence = assemble_trace_evidence(fixture["trace_id"], fixture["spans"])
    narrow = evidence.executables_by_span_id[original["span_id"]].stores["application"]
    wide = evidence.executables_by_span_id[sibling["span_id"]].stores["application"]
    assert narrow.reconstructable and wide.reconstructable
    assert narrow.start.value == {"value": "tool"}
    assert wide.start.value == {"value": "prepared"}
    assert narrow.transition_count == 1 and wide.transition_count == 3
    assert len(evidence.stores_by_id[wide.store_id].transitions) == 3


def test_composable_store_projection_is_current():
    from tests.generate_composable_store_projection import OUTPUT, render_projection

    assert OUTPUT.read_text() == render_projection()
