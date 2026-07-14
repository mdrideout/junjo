"""Canonical-fixture conformance for the Agent semantic backend."""

from __future__ import annotations

import copy
import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.features.agent_diagnostics.assembler import _requested_calls, assemble_agent_detail
from app.features.agent_diagnostics.contract import AgentDefinitionContext, AgentEvidenceError

GENERATOR_PATH = Path(__file__).parent / "generate_agent_semantic_projections.py"
SPEC = importlib.util.spec_from_file_location("agent_projection_generator", GENERATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


def _bounded_semantic_scalar_mutations() -> list[tuple[str, int, str, str, object]]:
    """Sample every consumed semantic attribute role in four canonical contexts."""
    contexts = (
        ("direct_typed_completion", 0),
        ("malformed_tool_arguments", 0),
        ("boundary_input_history_rejection", 0),
        ("tool_invokes_nested_workflow", 0),
    )
    mutations: list[tuple[str, int, str, str, object]] = []
    for fixture_name, owner_index in contexts:
        fixture = json.loads(
            (GENERATOR.FIXTURE_ROOT / "producer" / f"{fixture_name}.json").read_text()
        )
        owners = [
            span
            for span in fixture["spans"]
            if span["attributes_json"].get("junjo.span_type") == "agent"
        ]
        owner = owners[owner_index]
        runtime_id = owner["attributes_json"]["junjo.agent.runtime_id"]
        evidence_spans = [
            span
            for span in fixture["spans"]
            if span is owner
            or span["attributes_json"].get("junjo.agent.runtime_id") == runtime_id
            or span.get("parent_span_id")
            in {
                operation["span_id"]
                for operation in fixture["spans"]
                if operation["attributes_json"].get("junjo.agent.runtime_id") == runtime_id
                and "junjo.agent.operation_type" in operation["attributes_json"]
            }
        ]
        seen_roles: set[str] = set()
        for span in evidence_spans:
            for key in span["attributes_json"]:
                consumed = (
                    key.startswith("junjo.agent.")
                    or key.startswith("junjo.executable_")
                    or key.startswith("junjo.parent_executable_")
                    or key.startswith("junjo.store.")
                    or key
                    in {
                        "junjo.telemetry.contract_version",
                        "junjo.span_type",
                        "junjo.cancelled",
                        "junjo.cancelled_reason",
                        "error.type",
                    }
                )
                if not consumed or key in seen_roles:
                    continue
                seen_roles.add(key)
                for malformed in ({}, []):
                    mutations.append((fixture_name, owner_index, span["span_id"], key, malformed))
    return mutations


SEMANTIC_SCALAR_MUTATIONS = _bounded_semantic_scalar_mutations()


def test_generated_agent_semantic_projections_are_current() -> None:
    """The frontend artifact must be exactly the current backend projection."""
    assert GENERATOR.OUTPUT_PATH.read_text() == GENERATOR.render_projections()


def test_owner_from_separate_query_is_matched_by_transport_identity() -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "direct_typed_completion.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )

    detail = assemble_agent_detail(copy.deepcopy(owner), fixture["spans"])

    assert detail.integrity.status == "complete"
    assert "store_causal_owner_mismatch" not in {
        diagnostic.code for diagnostic in detail.integrity.diagnostics
    }


def test_state_unavailable_agent_ignores_unrelated_workflow_store_event() -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "boundary_input_history_rejection.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = fixture["spans"][0]
    unrelated_workflow = copy.deepcopy(owner)
    unrelated_workflow["span_id"] = "ffffffffffffffff"
    unrelated_workflow["name"] = "Unrelated Workflow"
    unrelated_workflow["attributes_json"] = {
        "junjo.telemetry.contract_version": 2,
        "junjo.span_type": "workflow",
        "junjo.executable_runtime_id": "workflow-run",
    }
    unrelated_workflow["events_json"] = [
        {
            "name": "set_state",
            "attributes": {"junjo.store.id": "workflow-store"},
        }
    ]
    fixture["spans"].append(unrelated_workflow)

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.state.reconstruction_status == "not_applicable"
    assert detail.integrity.status == "complete"


def test_state_unavailable_agent_rejects_store_event_on_its_owner_span() -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "boundary_input_history_rejection.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = fixture["spans"][0]
    owner["events_json"].append(
        {
            "name": "set_state",
            "attributes": {"junjo.store.id": "fabricated-store"},
        }
    )

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.integrity.status == "partial"
    assert "fabricated_boundary_store" in {
        diagnostic.code for diagnostic in detail.integrity.diagnostics
    }


def test_agent_store_excludes_transition_on_noncanonical_operation_span() -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "direct_typed_completion.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    operation = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.agent.operation_type") == "model_request"
    )
    operation["span_id"] = "not-a-span-id"

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.integrity.status == "partial"
    assert detail.state.reconstruction_status == "failed"
    assert all(transition.span_id != "not-a-span-id" for transition in detail.state.transitions)
    assert "invalid_span_id" in {diagnostic.code for diagnostic in detail.integrity.diagnostics}


@pytest.mark.parametrize(
    "case",
    SEMANTIC_SCALAR_MUTATIONS,
    ids=lambda case: f"{case[0]}-{case[3]}-{type(case[4]).__name__}",
)
def test_bounded_semantic_scalar_mutations_never_escape_typed_evidence_handling(
    case: tuple[str, int, str, str, object],
) -> None:
    fixture_name, owner_index, target_span_id, key, malformed = case
    fixture = copy.deepcopy(
        json.loads((GENERATOR.FIXTURE_ROOT / "producer" / f"{fixture_name}.json").read_text())
    )
    owners = [
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    ]
    owner = owners[owner_index]
    target = next(span for span in fixture["spans"] if span["span_id"] == target_span_id)
    target["attributes_json"][key] = copy.deepcopy(malformed)

    try:
        detail = assemble_agent_detail(owner, fixture["spans"])
    except AgentEvidenceError as error:
        assert error.diagnostics
    else:
        assert detail.integrity.status == "partial"
        assert detail.integrity.diagnostics


def test_generated_agent_semantic_projections_cover_every_valid_owner() -> None:
    projections = json.loads(GENERATOR.OUTPUT_PATH.read_text())
    owner_count = 0
    for fixture_path in GENERATOR.fixture_paths():
        fixture = json.loads(fixture_path.read_text())
        owner_count += sum(
            span["attributes_json"].get("junjo.span_type") == "agent" for span in fixture["spans"]
        )
    assert len(projections) == owner_count
    assert len({projection["case_name"] for projection in projections}) == owner_count


def test_unknown_tool_reason_identifies_only_the_undeclared_call_in_a_rejected_batch() -> None:
    definition = AgentDefinitionContext(
        agent_key="agent",
        instructions="",
        tools=[],
        tool_structural_ids={"lookup": "tool_sha256:" + "0" * 64},
        output_schema={},
    )
    calls, next_ordinal = _requested_calls(
        {
            "type": "tool_calls",
            "calls": [
                {"id": "known-call", "name": "lookup", "arguments": {}},
                {"id": "unknown-call", "name": "missing", "arguments": {}},
            ],
        },
        [],
        set(),
        "unknown_tool",
        1,
        definition,
        [],
    )

    assert next_ordinal == 3
    assert [(call.call_id, call.reason) for call in calls] == [
        ("known-call", "batch_preflight_rejected"),
        ("unknown-call", "unknown_tool"),
    ]


def test_redacted_operation_payloads_do_not_create_false_integrity_failures() -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "direct_typed_completion.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    model = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.agent.operation_type") == "model_request"
    )
    attributes = model["attributes_json"]
    for root, value in (
        ("junjo.agent.model.request", {"request": "redacted"}),
        ("junjo.agent.model.response_candidate", {"candidate": "redacted"}),
        ("junjo.agent.model.response", {"response": "redacted"}),
    ):
        attributes[root] = json.dumps(value)
        attributes[f"{root}.mode"] = "redacted"
        attributes[f"{root}.policy"] = "fixture.redacted.v1"

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.integrity.status == "complete"
    assert detail.operations[0].response_type == "final_output"
    assert detail.operations[0].usage is not None


def test_schema_shaped_redacted_definition_is_not_treated_as_original_content() -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "direct_typed_completion.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    attributes = owner["attributes_json"]
    definition = json.loads(attributes["junjo.agent.definition_snapshot"])
    definition["agentKey"] = "redacted-agent-key"
    definition["structuralId"] = f"agent_sha256:{'0' * 64}"
    attributes["junjo.agent.definition_snapshot"] = json.dumps(definition)
    attributes["junjo.agent.definition_snapshot.mode"] = "redacted"
    attributes["junjo.agent.definition_snapshot.policy"] = "fixture.redacted.v1"

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.integrity.status == "complete"
    assert detail.definition.mode == "redacted"


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda definition: definition["model"]["settings"].update({"unsafeInteger": 2**53}),
            "nonportable_json_value",
        ),
        (
            lambda definition: definition.update({"instructions": "\ud800"}),
            "nonportable_json_value",
        ),
    ],
    ids=["unsafe_integer", "invalid_unicode_surrogate"],
)
def test_noncanonical_full_definition_is_partial_not_an_assembler_crash(
    mutate: Callable[[dict[str, Any]], None],
    expected_code: str,
) -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "direct_typed_completion.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    attributes = owner["attributes_json"]
    definition = json.loads(attributes["junjo.agent.definition_snapshot"])
    mutate(definition)
    attributes["junjo.agent.definition_snapshot"] = json.dumps(definition)

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.integrity.status == "partial"
    assert expected_code in {diagnostic.code for diagnostic in detail.integrity.diagnostics}


@pytest.mark.parametrize(
    ("events", "expected_code"),
    [
        (None, "missing_operation_event_evidence"),
        ({"not": "a list"}, "invalid_operation_event_evidence"),
        (["not an event"], "invalid_operation_event_evidence"),
    ],
    ids=["missing", "invalid_container", "invalid_entry"],
)
def test_malformed_operation_event_evidence_is_partial_not_an_assembler_crash(
    events: Any,
    expected_code: str,
) -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "direct_typed_completion.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    model = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.agent.operation_type") == "model_request"
    )
    model["events_json"] = events

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.integrity.status == "partial"
    assert expected_code in {diagnostic.code for diagnostic in detail.integrity.diagnostics}


def test_observed_tool_operation_survives_unknown_admission_when_store_replay_is_partial() -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "ordered_multiple_tools.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    first_store_event = next(
        event
        for span in fixture["spans"]
        for event in span["events_json"]
        if event["name"] == "set_state"
    )
    first_store_event["attributes"].pop("junjo.store.action")

    detail = assemble_agent_detail(owner, fixture["spans"])

    requested_calls = [
        call
        for operation in detail.operations
        if operation.operation_type == "model_request"
        for call in operation.requested_tool_calls
    ]
    assert detail.integrity.status == "partial"
    assert requested_calls
    assert any(
        call.observed_tool_operation
        and call.admission == "unknown"
        and call.reason == "store_evidence_unavailable"
        for call in requested_calls
    )


def test_agent_store_event_on_unowned_span_is_diagnostic_not_replayed() -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "direct_typed_completion.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    model = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.agent.operation_type") == "model_request"
    )
    unrelated = copy.deepcopy(model)
    unrelated["span_id"] = "ffffffffffffffff"
    unrelated["parent_span_id"] = None
    unrelated["attributes_json"] = {"junjo.telemetry.contract_version": 2}
    unrelated["events_json"] = [copy.deepcopy(model["events_json"][0])]
    fixture["spans"].append(unrelated)

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.integrity.status == "partial"
    assert detail.state.reconstructable is True
    assert "store_causal_owner_mismatch" in {issue.code for issue in detail.integrity.diagnostics}


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("unsupported_contract", "unsupported_contract"),
        ("missing_contract", "unsupported_contract"),
        ("owner_key", "operation_owner_mismatch"),
        ("physical_parent", "operation_owner_mismatch"),
    ],
)
def test_ineligible_operation_evidence_cannot_verify_agent_store_replay(
    mutation: str,
    expected_code: str,
) -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "direct_typed_completion.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    model = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.agent.operation_type") == "model_request"
    )
    if mutation == "unsupported_contract":
        model["attributes_json"]["junjo.telemetry.contract_version"] = 1
    elif mutation == "missing_contract":
        model["attributes_json"].pop("junjo.telemetry.contract_version")
    elif mutation == "owner_key":
        model["attributes_json"]["junjo.agent.key"] = "different-agent"
    else:
        model["parent_span_id"] = "ffffffffffffffff"

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.integrity.status == "partial"
    assert detail.state.reconstruction_status == "failed"
    assert detail.state.reconstructable is False
    assert expected_code in {diagnostic.code for diagnostic in detail.integrity.diagnostics}


@pytest.mark.parametrize(
    ("case", "fixture_name", "expected_code"),
    [
        ("owner_type", "direct_typed_completion.json", "invalid_agent_owner_type"),
        ("owner_outcome", "direct_typed_completion.json", "invalid_terminal_fact"),
        ("operation_type", "direct_typed_completion.json", "invalid_operation_type"),
        ("payload_mode", "direct_typed_completion.json", "invalid_payload_slot"),
        ("response_type", "direct_typed_completion.json", "invalid_model_response"),
        ("limit_kind", "model_request_limit_exhaustion.json", "invalid_limit_evidence"),
        (
            "parent_type",
            "nested_agent_owner_isolation.json",
            "parent_executable_correspondence_mismatch",
        ),
        (
            "nested_executable_type",
            "tool_invokes_nested_workflow.json",
            "invalid_nested_executable",
        ),
    ],
)
@pytest.mark.parametrize("malformed", [{}, []], ids=["object", "array"])
def test_unhashable_semantic_scalar_evidence_never_crashes_agent_assembly(
    case: str,
    fixture_name: str,
    expected_code: str,
    malformed: Any,
) -> None:
    fixture = copy.deepcopy(
        json.loads((GENERATOR.FIXTURE_ROOT / "producer" / fixture_name).read_text())
    )
    owners = [
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    ]
    owner = (
        next(span for span in owners if "junjo.parent_executable_type" in span["attributes_json"])
        if case == "parent_type"
        else owners[0]
    )
    if case == "owner_type":
        owner["attributes_json"]["junjo.span_type"] = malformed
    elif case == "owner_outcome":
        owner["attributes_json"]["junjo.agent.outcome"] = malformed
    elif case == "operation_type":
        operation = next(
            span
            for span in fixture["spans"]
            if "junjo.agent.operation_type" in span["attributes_json"]
        )
        operation["attributes_json"]["junjo.agent.operation_type"] = malformed
    elif case == "payload_mode":
        owner["attributes_json"]["junjo.agent.definition_snapshot.mode"] = malformed
    elif case == "response_type":
        model = next(
            span
            for span in fixture["spans"]
            if span["attributes_json"].get("junjo.agent.operation_type") == "model_request"
        )
        model["attributes_json"]["junjo.agent.model.response_type"] = malformed
    elif case == "limit_kind":
        owner["attributes_json"]["junjo.agent.limit.exceeded"] = malformed
    elif case == "parent_type":
        owner["attributes_json"]["junjo.parent_executable_type"] = malformed
    else:
        nested = next(
            span
            for span in fixture["spans"]
            if span["attributes_json"].get("junjo.span_type") == "workflow"
        )
        nested["attributes_json"]["junjo.span_type"] = malformed

    try:
        detail = assemble_agent_detail(owner, fixture["spans"])
    except AgentEvidenceError as error:
        observed = {diagnostic.code for diagnostic in error.diagnostics}
    else:
        assert detail.integrity.status == "partial"
        observed = {diagnostic.code for diagnostic in detail.integrity.diagnostics}

    assert expected_code in observed


def test_non_completed_agent_omits_unexpected_output_as_partial_evidence() -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "over_budget_tool_batch.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    attributes = owner["attributes_json"]
    attributes["junjo.agent.output"] = "null"
    attributes["junjo.agent.output.mode"] = "full"
    attributes["junjo.agent.output.policy"] = "junjo.full.v1"

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.summary.outcome == "failed"
    assert detail.output is None
    assert detail.integrity.status == "partial"
    assert "unexpected_output_evidence" in {
        diagnostic.code for diagnostic in detail.integrity.diagnostics
    }


@pytest.mark.parametrize("malformed", [{}, []], ids=["object", "array"])
def test_nonscalar_store_action_is_partial_not_an_assembler_crash(malformed: Any) -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "direct_typed_completion.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    first_store_event = next(
        event
        for span in fixture["spans"]
        for event in span["events_json"]
        if event["name"] == "set_state"
    )
    first_store_event["attributes"]["junjo.store.action"] = malformed

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.integrity.status == "partial"
    assert "store_causal_owner_mismatch" in {
        diagnostic.code for diagnostic in detail.integrity.diagnostics
    }


def test_duplicate_payload_object_name_is_rejected_before_last_key_wins() -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "direct_typed_completion.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    attributes = owner["attributes_json"]
    raw = attributes["junjo.agent.definition_snapshot"]
    attributes["junjo.agent.definition_snapshot"] = '{"agentKey":"shadowed",' + raw[1:]

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.integrity.status == "partial"
    assert "duplicate_json_object_name" in {
        diagnostic.code for diagnostic in detail.integrity.diagnostics
    }


@pytest.mark.parametrize("parent_span_id", ["bad", "ABCDEF0123456789", "bad\ud800text"])
def test_malformed_ambient_parent_span_id_is_partial(parent_span_id: str) -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "direct_typed_completion.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    owner["parent_span_id"] = parent_span_id

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.integrity.status == "partial"
    assert detail.parent_executable is None
    assert "invalid_parent_executable" in {
        diagnostic.code for diagnostic in detail.integrity.diagnostics
    }


def test_operation_from_wrong_trace_is_not_admitted_to_owner_projection() -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "direct_typed_completion.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    operation = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.agent.operation_type") == "model_request"
    )
    operation["trace_id"] = "bad\ud800text"

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.integrity.status == "partial"
    assert detail.operations == []
    assert "operation_owner_mismatch" in {
        diagnostic.code for diagnostic in detail.integrity.diagnostics
    }


def test_inverted_operation_interval_is_omitted_with_typed_partial_evidence() -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "direct_typed_completion.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    operation = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.agent.operation_type") == "model_request"
    )
    operation["end_time"] = "2026-01-01T00:00:00+00:00"

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.integrity.status == "partial"
    assert detail.operations == []
    assert "invalid_span_interval" in {
        diagnostic.code for diagnostic in detail.integrity.diagnostics
    }


@pytest.mark.parametrize(
    ("scope", "key", "value", "remove"),
    [
        ("attributes", "junjo.executable_definition_id", None, False),
        ("attributes", "junjo.executable_runtime_id", 123, False),
        ("attributes", "junjo.executable_structural_id", "", False),
        ("span", "name", None, True),
        ("span", "span_id", None, False),
        ("span", "trace_id", 123, False),
    ],
    ids=[
        "null_definition",
        "wrong_runtime_type",
        "empty_structural_id",
        "missing_name",
        "null_span_id",
        "wrong_trace_type",
    ],
)
def test_malformed_nested_executable_identity_is_not_coerced(
    scope: str,
    key: str,
    value: Any,
    remove: bool,
) -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "tool_invokes_nested_workflow.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    tool = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.agent.operation_type") == "tool"
    )
    nested = next(
        span
        for span in fixture["spans"]
        if span.get("parent_span_id") == tool["span_id"]
        and span["attributes_json"].get("junjo.span_type") == "workflow"
    )
    target = nested["attributes_json"] if scope == "attributes" else nested
    if remove:
        target.pop(key)
    else:
        target[key] = value

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.integrity.status == "partial"
    assert detail.nested_executables == []
    assert {diagnostic.code for diagnostic in detail.integrity.diagnostics} & {
        "invalid_nested_executable",
        "invalid_nested_executable_parent",
    }


def test_unsupported_nested_executable_is_not_exposed_as_complete_evidence() -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "tool_invokes_nested_workflow.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    tool = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.agent.operation_type") == "tool"
    )
    nested = next(
        span
        for span in fixture["spans"]
        if span.get("parent_span_id") == tool["span_id"]
        and span["attributes_json"].get("junjo.span_type") == "workflow"
    )
    nested["attributes_json"]["junjo.telemetry.contract_version"] = 1

    detail = assemble_agent_detail(owner, fixture["spans"])

    assert detail.integrity.status == "partial"
    assert detail.nested_executables == []
    assert "unsupported_contract" in {
        diagnostic.code for diagnostic in detail.integrity.diagnostics
    }


def test_physical_parent_must_belong_to_declared_semantic_parent() -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "nested_agent_owner_isolation.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owners = [
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    ]
    nested_owner = next(span for span in owners if span.get("parent_span_id") is not None)
    unrelated_tool = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.agent.operation_type") == "tool"
    )
    nested_owner["parent_span_id"] = unrelated_tool["span_id"]

    detail = assemble_agent_detail(nested_owner, fixture["spans"])

    assert detail.integrity.status == "partial"
    assert detail.parent_executable is None
    assert "parent_executable_correspondence_mismatch" in {
        diagnostic.code for diagnostic in detail.integrity.diagnostics
    }


def test_owned_tool_may_physically_interpose_declared_agent_parent() -> None:
    fixture_path = GENERATOR.FIXTURE_ROOT / "producer" / "nested_agent_owner_isolation.json"
    fixture = copy.deepcopy(json.loads(fixture_path.read_text()))
    owners = [
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    ]
    outer_owner = next(span for span in owners if span.get("parent_span_id") is None)
    nested_owner = next(span for span in owners if span.get("parent_span_id") is not None)
    owned_tool = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.agent.operation_type") == "tool"
    )
    nested_owner["parent_span_id"] = owned_tool["span_id"]
    nested_attributes = nested_owner["attributes_json"]
    outer_attributes = outer_owner["attributes_json"]
    nested_attributes["junjo.parent_executable_type"] = "agent"
    for suffix in ("definition_id", "runtime_id", "structural_id"):
        nested_attributes[f"junjo.parent_executable_{suffix}"] = outer_attributes[
            f"junjo.executable_{suffix}"
        ]

    detail = assemble_agent_detail(nested_owner, fixture["spans"])

    assert detail.integrity.status == "complete"
    assert detail.parent_executable is not None
    assert detail.parent_executable.executable_type == "agent"
    assert detail.parent_executable.span_id == outer_owner["span_id"]
    assert detail.parent_executable.physical_parent_span_id == owned_tool["span_id"]


@pytest.mark.parametrize(
    "fixture_path",
    sorted(
        (
            GENERATOR.REPOSITORY_ROOT / "contracts" / "telemetry" / "fixtures" / "invalid" / "agent"
        ).glob("*.json")
    ),
    ids=lambda path: path.stem,
)
def test_invalid_agent_derivative_reports_declared_diagnostic(fixture_path: Path) -> None:
    wrapper = json.loads(fixture_path.read_text())
    fixture = wrapper["fixture"]
    owner = next(
        span
        for span in fixture["spans"]
        if span["attributes_json"].get("junjo.span_type") == "agent"
    )
    try:
        detail = assemble_agent_detail(owner, fixture["spans"])
    except AgentEvidenceError as error:
        observed = {diagnostic.code for diagnostic in error.diagnostics}
    else:
        observed = {diagnostic.code for diagnostic in detail.integrity.diagnostics}
    assert wrapper["expected_diagnostic"] in observed
