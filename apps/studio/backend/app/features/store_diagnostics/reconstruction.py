"""Owner-scoped Store reconstruction and evidence integrity verification."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

import jsonpatch

from app.features.store_diagnostics.payloads import parse_payload_slot
from app.features.store_diagnostics.schemas import (
    EvidenceDiagnostic,
    StoreDetail,
    StoreTransition,
)
from app.features.telemetry_contract.scalars import (
    is_contract_int,
    is_lower_hex,
    is_portable_text,
    portable_diagnostic_text,
)


@dataclass(frozen=True)
class StoreReconstructionResult:
    """Store projection plus diagnostics owned by the enclosing detail integrity."""

    detail: StoreDetail
    diagnostics: list[EvidenceDiagnostic]
    replay_verified: bool


@dataclass(frozen=True)
class StoreOwnerBoundary:
    """Executable-specific attribute names for one generic Store contract."""

    store_id_attribute: str
    state_start_root: str
    state_end_root: str
    availability_attribute: str | None = None
    unavailable_owner_prefixes: tuple[str, ...] = ()
    runtime_id_attribute: str | None = None


AGENT_STORE_BOUNDARY = StoreOwnerBoundary(
    store_id_attribute="junjo.agent.store.id",
    state_start_root="junjo.agent.state.start",
    state_end_root="junjo.agent.state.end",
    availability_attribute="junjo.agent.state.available",
    unavailable_owner_prefixes=(
        "junjo.agent.store",
        "junjo.agent.state.start",
        "junjo.agent.state.end",
        "junjo.store.",
    ),
    runtime_id_attribute="junjo.agent.runtime_id",
)

WORKFLOW_STORE_BOUNDARY = StoreOwnerBoundary(
    store_id_attribute="junjo.workflow.store.id",
    state_start_root="junjo.workflow.state.start",
    state_end_root="junjo.workflow.state.end",
)


def _diagnostic(code: str, path: str, message: str) -> EvidenceDiagnostic:
    return EvidenceDiagnostic(
        code=portable_diagnostic_text(code, fallback="invalid_evidence"),
        path=portable_diagnostic_text(path, fallback="evidence"),
        message=portable_diagnostic_text(
            message,
            fallback="Evidence contains nonportable diagnostic text.",
        ),
    )


def _is_nonnegative_int(value: Any) -> bool:
    """Return true only for contract integers; Python booleans are not integers here."""
    return is_contract_int(value)


def _transition_sort_key(item: tuple[str, dict[str, Any]]) -> tuple[int, int, str]:
    """Totally order valid and malformed events without comparing unrelated types."""
    attributes = item[1].get("attributes")
    sequence = (
        attributes.get("junjo.store.transition.sequence") if isinstance(attributes, dict) else None
    )
    if _is_nonnegative_int(sequence):
        return (0, sequence, item[0])
    return (1, 0, f"{type(sequence).__name__}:{sequence!r}:{item[0]}")


def _span_is_owned_by_unavailable_executable(
    span: dict[str, Any],
    owner_attributes: dict[str, Any],
    boundary: StoreOwnerBoundary,
) -> bool:
    """Attribute otherwise ownerless Store events using executable runtime identity."""

    if boundary.runtime_id_attribute is None:
        return False
    runtime_id = owner_attributes.get(boundary.runtime_id_attribute)
    span_attributes = span.get("attributes_json")
    return (
        is_portable_text(runtime_id, nonempty=True)
        and isinstance(span_attributes, dict)
        and span_attributes.get(boundary.runtime_id_attribute) == runtime_id
    )


def reconstruct_store(
    owner_attributes: dict[str, Any],
    spans: list[dict[str, Any]],
    boundary: StoreOwnerBoundary,
) -> StoreReconstructionResult:
    """Reconstruct one executable-owned Store from generic v2 evidence."""
    state_available = (
        owner_attributes.get(boundary.availability_attribute)
        if boundary.availability_attribute is not None
        else True
    )
    if boundary.availability_attribute is not None and state_available is False:
        forbidden_keys = {
            key
            for key in owner_attributes
            if any(key.startswith(prefix) for prefix in boundary.unavailable_owner_prefixes)
        }
        has_store_events = any(
            _span_is_owned_by_unavailable_executable(
                span,
                owner_attributes,
                boundary,
            )
            and isinstance(event, dict)
            and event.get("name") == "set_state"
            and isinstance(event.get("attributes"), dict)
            and "junjo.store.id" in event["attributes"]
            for span in spans
            for event in (
                span.get("events_json") if isinstance(span.get("events_json"), list) else []
            )
        )
        diagnostics = []
        if forbidden_keys or has_store_events:
            diagnostics.append(
                _diagnostic(
                    "fabricated_boundary_store",
                    boundary.availability_attribute,
                    "State-unavailable executable cannot carry Store facts or events.",
                )
            )
        return StoreReconstructionResult(
            detail=StoreDetail(
                available=False,
                reconstructable=False,
                reconstruction_status="not_applicable",
                reconstruction_reason="state_unavailable",
            ),
            diagnostics=diagnostics,
            replay_verified=False,
        )
    if boundary.availability_attribute is not None and state_available is not True:
        diagnostic = _diagnostic(
            "invalid_store_owner_fact",
            boundary.availability_attribute,
            "State availability is absent or invalid.",
        )
        return StoreReconstructionResult(
            detail=StoreDetail(
                available=False,
                reconstructable=False,
                reconstruction_status="not_applicable",
                reconstruction_reason="invalid_state_availability",
            ),
            diagnostics=[diagnostic],
            replay_verified=False,
        )

    diagnostics: list[EvidenceDiagnostic] = []
    store_id = owner_attributes.get(boundary.store_id_attribute)
    if not is_portable_text(store_id, nonempty=True):
        code = (
            "missing_store_id"
            if not isinstance(store_id, str) or not store_id
            else "nonportable_scalar_text"
        )
        diagnostics.append(
            _diagnostic(code, boundary.store_id_attribute, "Store ID is absent or invalid.")
        )
        return StoreReconstructionResult(
            detail=StoreDetail(
                available=True,
                reconstructable=False,
                reconstruction_status="failed",
                reconstruction_reason="missing_store_id",
            ),
            diagnostics=diagnostics,
            replay_verified=False,
        )

    start, issues = parse_payload_slot(
        owner_attributes,
        boundary.state_start_root,
        required=True,
    )
    diagnostics.extend(issues)
    end, issues = parse_payload_slot(
        owner_attributes,
        boundary.state_end_root,
        required=True,
    )
    diagnostics.extend(issues)
    revision_start = owner_attributes.get("junjo.store.revision.start")
    revision_end = owner_attributes.get("junjo.store.revision.end")
    transition_count = owner_attributes.get("junjo.store.transition.count")
    reconstructable_claimed = owner_attributes.get("junjo.store.reconstructable")
    for key, value in (
        ("junjo.store.revision.start", revision_start),
        ("junjo.store.revision.end", revision_end),
        ("junjo.store.transition.count", transition_count),
    ):
        if not _is_nonnegative_int(value):
            diagnostics.append(_diagnostic("invalid_store_owner_fact", key, f"{key} is invalid."))
    if not isinstance(reconstructable_claimed, bool):
        diagnostics.append(
            _diagnostic(
                "invalid_store_owner_fact",
                "junjo.store.reconstructable",
                "Reconstructability claim is invalid.",
            )
        )
        reconstructable_claimed = None

    raw_events: list[tuple[str, dict[str, Any]]] = []
    observed_store_name: str | None = None
    for span_index, span in enumerate(spans):
        span_id = span.get("span_id")
        valid_span_id = is_lower_hex(span_id, length=16)
        invalid_span_id_diagnosed = False
        events = span.get("events_json", [])
        if not isinstance(events, list):
            diagnostics.append(
                _diagnostic(
                    "invalid_store_event", f"spans[{span_index}].events", "Events are invalid."
                )
            )
            continue
        for event_index, event in enumerate(events):
            if not isinstance(event, dict):
                diagnostics.append(
                    _diagnostic(
                        "invalid_store_event",
                        f"spans[{span_index}].events[{event_index}]",
                        "Store event is invalid.",
                    )
                )
                continue
            attributes = event.get("attributes")
            if (
                event.get("name") == "set_state"
                and isinstance(attributes, dict)
                and attributes.get("junjo.store.id") == store_id
            ):
                if not valid_span_id:
                    if not invalid_span_id_diagnosed:
                        diagnostics.append(
                            _diagnostic(
                                "invalid_span_id",
                                f"spans[{span_index}].span_id",
                                "Store transition carrier span ID must be 16 lowercase hexadecimal characters.",
                            )
                        )
                        invalid_span_id_diagnosed = True
                    continue
                assert isinstance(span_id, str)
                store_name = attributes.get("junjo.store.name")
                if not is_portable_text(store_name, nonempty=True):
                    diagnostics.append(
                        _diagnostic(
                            "invalid_store_name",
                            f"spans[{span_index}].events[{event_index}].junjo.store.name",
                            "Store transition name is absent or invalid.",
                        )
                    )
                elif observed_store_name is None:
                    observed_store_name = store_name
                elif store_name != observed_store_name:
                    diagnostics.append(
                        _diagnostic(
                            "invalid_store_name",
                            f"spans[{span_index}].events[{event_index}].junjo.store.name",
                            "One Store ID must use one consistent Store name.",
                        )
                    )
                raw_events.append((span_id, event))

    sequences = [
        event["attributes"].get("junjo.store.transition.sequence") for _, event in raw_events
    ]
    integer_sequences = [value for value in sequences if _is_nonnegative_int(value)]
    if len(integer_sequences) != len(sequences):
        diagnostics.append(
            _diagnostic(
                "transition_sequence_out_of_range", "events", "A transition sequence is invalid."
            )
        )
    if len(integer_sequences) != len(set(integer_sequences)):
        diagnostics.append(
            _diagnostic(
                "transition_sequence_duplicate", "events", "Transition sequences are duplicated."
            )
        )
    if _is_nonnegative_int(transition_count):
        expected = list(range(1, transition_count + 1))
        observed = sorted(integer_sequences)
        if observed != expected:
            code = (
                "transition_sequence_missing_trailing"
                if observed == list(range(1, len(observed) + 1))
                else "transition_sequence_gap"
            )
            diagnostics.append(_diagnostic(code, "events", "Transition sequence is incomplete."))

    transitions: list[StoreTransition] = []
    payload_mode = start.mode if start is not None else None
    payload_policy = start.policy if start is not None else None
    inline_replay = (
        start is not None
        and end is not None
        and start.mode in {"full", "redacted"}
        and end.mode == start.mode
        and end.policy == start.policy
    )
    policy_unavailable = (
        start is not None
        and end is not None
        and start.mode in {"excluded", "reference"}
        and end.mode == start.mode
        and end.policy == start.policy
    )
    if start is not None and end is not None and not inline_replay and not policy_unavailable:
        diagnostics.append(
            _diagnostic(
                "payload_policy_mismatch",
                f"{boundary.state_start_root}/{boundary.state_end_root}",
                "Store start and end evidence must use one comparable payload mode and policy.",
            )
        )
    current_state = copy.deepcopy(start.value) if inline_replay else None
    current_revision = revision_start if _is_nonnegative_int(revision_start) else None
    replay_possible = inline_replay and not diagnostics
    for span_id, event in sorted(raw_events, key=_transition_sort_key):
        attributes = event["attributes"]
        sequence = attributes.get("junjo.store.transition.sequence")
        before_revision = attributes.get("junjo.store.revision.before")
        after_revision = attributes.get("junjo.store.revision.after")
        if (
            not all(
                _is_nonnegative_int(value) for value in (sequence, before_revision, after_revision)
            )
            or sequence == 0
        ):
            diagnostics.append(
                _diagnostic(
                    "invalid_store_transition",
                    "events",
                    "Transition sequence and revisions must be non-negative contract integers.",
                )
            )
            replay_possible = False
            continue
        event_id = attributes.get("id")
        action = attributes.get("junjo.store.action")
        if not is_portable_text(event_id, nonempty=True):
            diagnostics.append(
                _diagnostic(
                    "missing_transition_event_id"
                    if not isinstance(event_id, str) or not event_id
                    else "nonportable_scalar_text",
                    f"events[{sequence}].id",
                    "Event ID is absent or invalid.",
                )
            )
            replay_possible = False
            continue
        if not is_portable_text(action, nonempty=True):
            diagnostics.append(
                _diagnostic(
                    "missing_transition_action"
                    if not isinstance(action, str) or not action
                    else "nonportable_scalar_text",
                    f"events[{sequence}].junjo.store.action",
                    "Store action is absent.",
                )
            )
            replay_possible = False
            continue
        patch, issues = parse_payload_slot(attributes, "junjo.state_json_patch", required=True)
        diagnostics.extend(issues)
        if patch is None or patch.mode != payload_mode or patch.policy != payload_policy:
            diagnostics.append(
                _diagnostic(
                    "payload_policy_mismatch",
                    f"events[{sequence}].junjo.state_json_patch",
                    "Store transition evidence must use the start-state payload mode and policy.",
                )
            )
            replay_possible = False
            policy_unavailable = False
        before_state = copy.deepcopy(current_state) if replay_possible else None
        after_state = None
        if current_revision is not None and before_revision != current_revision:
            diagnostics.append(
                _diagnostic(
                    "revision_discontinuity",
                    f"events[{sequence}]",
                    "Revision-before does not match the preceding revision.",
                )
            )
            replay_possible = False
        valid_revision_step = after_revision in {before_revision, before_revision + 1}
        if not valid_revision_step:
            diagnostics.append(
                _diagnostic(
                    "revision_discontinuity",
                    f"events[{sequence}]",
                    "Revision-after must stay equal or increment by one.",
                )
            )
            replay_possible = False
        if (
            replay_possible
            and patch is not None
            and patch.mode in {"full", "redacted"}
            and isinstance(patch.value, list)
        ):
            try:
                current_state = jsonpatch.JsonPatch(patch.value).apply(
                    current_state, in_place=False
                )
                after_state = copy.deepcopy(current_state)
            except (jsonpatch.JsonPatchException, TypeError, ValueError) as error:
                diagnostics.append(
                    _diagnostic(
                        "patch_replay_mismatch",
                        f"events[{sequence}]",
                        f"Patch replay failed: {error}",
                    )
                )
                replay_possible = False
        elif inline_replay:
            replay_possible = False
        current_revision = after_revision
        if not valid_revision_step:
            continue
        transitions.append(
            StoreTransition(
                sequence=sequence,
                revision_before=before_revision,
                revision_after=after_revision,
                span_id=span_id,
                event_id=event_id,
                action=action,
                patch=patch,
                before=before_state,
                after=after_state,
            )
        )

    if current_revision != revision_end:
        diagnostics.append(
            _diagnostic(
                "terminal_revision_mismatch",
                "junjo.store.revision.end",
                "Terminal revision does not match the transition chain.",
            )
        )
        replay_possible = False
    if inline_replay and current_state != end.value:
        diagnostics.append(
            _diagnostic(
                "patch_replay_mismatch",
                boundary.state_end_root,
                "Replayed state does not exactly match emitted end state.",
            )
        )
        replay_possible = False

    replay_verified = replay_possible and not diagnostics
    if reconstructable_claimed is True and not replay_verified:
        diagnostics.append(
            _diagnostic(
                "reconstructable_claim_mismatch",
                "junjo.store.reconstructable",
                "Producer claimed reconstructability but independent replay failed.",
            )
        )

    if replay_verified:
        reconstruction_status = "verified"
        reconstruction_reason = None
    elif policy_unavailable and not diagnostics:
        reconstruction_status = "policy_unavailable"
        reconstruction_reason = "payload_policy"
    else:
        reconstruction_status = "failed"
        reconstruction_reason = diagnostics[0].code if diagnostics else "replay_unavailable"

    return StoreReconstructionResult(
        detail=StoreDetail(
            available=True,
            store_id=store_id,
            revision_start=revision_start if _is_nonnegative_int(revision_start) else None,
            revision_end=revision_end if _is_nonnegative_int(revision_end) else None,
            transition_count=transition_count if _is_nonnegative_int(transition_count) else 0,
            reconstructable_claimed=bool(reconstructable_claimed),
            reconstructable=replay_verified,
            reconstruction_status=reconstruction_status,
            reconstruction_reason=reconstruction_reason,
            start=start,
            end=end,
            transitions=transitions,
        ),
        diagnostics=diagnostics,
        replay_verified=replay_verified,
    )
