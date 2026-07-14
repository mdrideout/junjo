"""Conformance tests for authoritative Workflow Store diagnostics."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from app.features.workflow_diagnostics.assembler import assemble_workflow_store_diagnostic

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[4] / "contracts" / "telemetry" / "fixtures" / "workflow"
)
GENERATOR_PATH = Path(__file__).parent / "generate_workflow_store_projections.py"
SPEC = importlib.util.spec_from_file_location(
    "workflow_store_projection_generator",
    GENERATOR_PATH,
)
assert SPEC is not None and SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)
def _workflow_cases() -> list[tuple[str, dict, list[dict]]]:
    cases = []
    for path in sorted(FIXTURE_ROOT.glob("*.json")):
        fixture = json.loads(path.read_text())
        for owner in fixture["spans"]:
            executable_type = owner["attributes_json"].get("junjo.span_type")
            if executable_type in {"workflow", "subflow"}:
                cases.append(
                    (
                        f"{path.stem}:{owner['span_id']}",
                        owner,
                        fixture["spans"],
                    )
                )
    return cases


@pytest.mark.parametrize(
    ("_name", "owner", "spans"),
    _workflow_cases(),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_every_canonical_workflow_store_is_backend_verified(
    _name: str,
    owner: dict,
    spans: list[dict],
) -> None:
    detail = assemble_workflow_store_diagnostic(owner, spans)

    assert detail.state.reconstruction_status == "verified"
    assert detail.state.reconstructable is True
    assert detail.integrity.status == "complete"
    assert detail.integrity.diagnostics == []


def test_generated_workflow_store_projections_are_current() -> None:
    assert GENERATOR.OUTPUT_PATH.read_text() == GENERATOR.render_projections()


def test_generated_workflow_store_projections_cover_every_owner() -> None:
    projections = json.loads(GENERATOR.OUTPUT_PATH.read_text())
    expected_case_names = {name for name, _owner, _spans in _workflow_cases()}

    assert {projection["case_name"] for projection in projections} == expected_case_names


def test_workflow_store_unsafe_scalar_becomes_partial_not_unsafe_json() -> None:
    _name, owner, spans = _workflow_cases()[0]
    owner = copy.deepcopy(owner)
    spans = [
        owner if span["span_id"] == owner["span_id"] else copy.deepcopy(span) for span in spans
    ]
    owner["attributes_json"]["junjo.store.revision.end"] = 2**53

    detail = assemble_workflow_store_diagnostic(owner, spans)

    assert detail.integrity.status == "partial"
    assert detail.state.revision_end is None
    assert "invalid_store_owner_fact" in {issue.code for issue in detail.integrity.diagnostics}


def test_workflow_store_excessive_payload_nesting_is_typed_partial_evidence() -> None:
    _name, original_owner, original_spans = _workflow_cases()[0]
    spans = copy.deepcopy(original_spans)
    owner = next(span for span in spans if span["span_id"] == original_owner["span_id"])
    nested: object = "leaf"
    for _ in range(130):
        nested = [nested]
    owner["attributes_json"]["junjo.workflow.state.start"] = json.dumps(nested)

    detail = assemble_workflow_store_diagnostic(owner, spans)

    assert detail.integrity.status == "partial"
    assert "payload_nesting_too_deep" in {issue.code for issue in detail.integrity.diagnostics}


@pytest.mark.parametrize(
    ("version", "expected_code"),
    [
        (1, "unsupported_contract"),
        (None, "missing_contract_version"),
    ],
    ids=["unsupported", "missing"],
)
def test_workflow_store_excludes_child_evidence_without_active_contract(
    version: int | None,
    expected_code: str,
) -> None:
    _name, original_owner, original_spans = next(
        case for case in _workflow_cases() if case[0].startswith("basic_workflow_success:")
    )
    spans = copy.deepcopy(original_spans)
    owner = next(span for span in spans if span["span_id"] == original_owner["span_id"])
    child = next(span for span in spans if span["name"] == "fetch_input")
    if version is None:
        child["attributes_json"].pop("junjo.telemetry.contract_version")
    else:
        child["attributes_json"]["junjo.telemetry.contract_version"] = version

    detail = assemble_workflow_store_diagnostic(owner, spans)

    assert detail.integrity.status == "partial"
    assert detail.state.reconstruction_status == "failed"
    assert all(transition.span_id != child["span_id"] for transition in detail.state.transitions)
    assert expected_code in {issue.code for issue in detail.integrity.diagnostics}


def test_workflow_store_excludes_transition_on_noncanonical_carrier_span() -> None:
    _name, original_owner, original_spans = next(
        case for case in _workflow_cases() if case[0].startswith("basic_workflow_success:")
    )
    spans = copy.deepcopy(original_spans)
    owner = next(span for span in spans if span["span_id"] == original_owner["span_id"])
    event_span = next(
        span
        for span in spans
        if span is not owner
        and any(event.get("name") == "set_state" for event in span["events_json"])
    )
    event_span["span_id"] = "not-a-span-id"

    detail = assemble_workflow_store_diagnostic(owner, spans)

    assert detail.integrity.status == "partial"
    assert detail.state.reconstruction_status == "failed"
    assert all(transition.span_id != "not-a-span-id" for transition in detail.state.transitions)
    assert "invalid_span_id" in {issue.code for issue in detail.integrity.diagnostics}
