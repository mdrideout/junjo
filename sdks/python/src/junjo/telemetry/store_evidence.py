"""Generic Store transition ordering and reconstruction evidence."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

import jsonpatch

from .payload import FULL_PAYLOAD_POLICY, encode_json


@dataclass(frozen=True, slots=True)
class StoreTransitionEvidence:
    """One successfully validated Store action in lock order."""

    sequence: int
    revision_before: int
    revision_after: int
    patch: tuple[dict[str, Any], ...]

    @property
    def patch_json(self) -> str:
        return encode_json(list(self.patch))


@dataclass(frozen=True, slots=True)
class StoreOwnerEvidence:
    """Terminal owner facts for one Store execution."""

    state_start: Any
    state_end: Any
    revision_start: int
    revision_end: int
    transition_count: int
    reconstructable: bool


class StoreEvidenceTracker:
    """Retain full-policy transition facts independently from OpenTelemetry export."""

    def __init__(self, initial_projection: Any) -> None:
        self._state_start = copy.deepcopy(initial_projection)
        self._revision = 0
        self._transitions: list[StoreTransitionEvidence] = []

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def transition_count(self) -> int:
        return len(self._transitions)

    @property
    def state_start(self) -> Any:
        return copy.deepcopy(self._state_start)

    def record(
        self,
        *,
        projection_before: Any,
        projection_after: Any,
        live_state_changed: bool,
    ) -> StoreTransitionEvidence:
        raw_patch, encoded_patch = self._validated_patch(
            projection_before,
            projection_after,
        )
        revision_before = self._revision
        revision_after = revision_before + (1 if live_state_changed else 0)
        transition = StoreTransitionEvidence(
            sequence=len(self._transitions) + 1,
            revision_before=revision_before,
            revision_after=revision_after,
            patch=tuple(copy.deepcopy(raw_patch)),
        )
        # ``patch_json`` must remain an exact deterministic projection of the
        # value proven portable before mutation.
        if transition.patch_json != encoded_patch:
            raise ValueError("Store transition patch encoding was not deterministic.")
        self._revision = revision_after
        self._transitions.append(transition)
        return transition

    def validate_transition(self, *, projection_before: Any, projection_after: Any) -> None:
        """Prove an exact RFC 6902 transition is portable without mutation."""

        self._validated_patch(projection_before, projection_after)

    @staticmethod
    def _validated_patch(
        projection_before: Any,
        projection_after: Any,
    ) -> tuple[list[dict[str, Any]], str]:
        """Build and validate a complete patch before any evidence commit."""

        raw_patch = jsonpatch.make_patch(projection_before, projection_after).patch
        # A valid state can still produce an over-depth JSON Patch because each
        # changed value is wrapped by the patch array and operation object.
        return raw_patch, encode_json(raw_patch)

    def finalize(self, state_end: Any) -> StoreOwnerEvidence:
        end = copy.deepcopy(state_end)
        replay = copy.deepcopy(self._state_start)
        expected_revision = 0
        reconstructable = True
        for expected_sequence, transition in enumerate(self._transitions, start=1):
            if transition.sequence != expected_sequence:
                reconstructable = False
            if transition.revision_before != expected_revision:
                reconstructable = False
            if transition.revision_after not in (
                transition.revision_before,
                transition.revision_before + 1,
            ):
                reconstructable = False
            expected_revision = transition.revision_after
            try:
                replay = jsonpatch.JsonPatch(list(transition.patch)).apply(replay, in_place=False)
            except Exception:
                reconstructable = False
        if expected_revision != self._revision or replay != end:
            reconstructable = False
        return StoreOwnerEvidence(
            state_start=self.state_start,
            state_end=end,
            revision_start=0,
            revision_end=self._revision,
            transition_count=len(self._transitions),
            reconstructable=reconstructable,
        )

    def transition_attributes(self, transition: StoreTransitionEvidence) -> dict[str, str | int]:
        return {
            "junjo.store.transition.sequence": transition.sequence,
            "junjo.store.revision.before": transition.revision_before,
            "junjo.store.revision.after": transition.revision_after,
            "junjo.state_json_patch": transition.patch_json,
            "junjo.state_json_patch.mode": "full",
            "junjo.state_json_patch.policy": FULL_PAYLOAD_POLICY,
        }
