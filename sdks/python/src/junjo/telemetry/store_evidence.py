"""Generic Store transition ordering and reconstruction evidence."""

from __future__ import annotations

import copy
from collections import deque
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


@dataclass(frozen=True, slots=True, eq=False)
class StoreBoundary:
    """One execution's starting checkpoint; identity distinguishes equal starts."""

    state: Any
    revision: int
    sequence: int


@dataclass(frozen=True, slots=True)
class StoreOwnerEvidence:
    """Terminal owner facts for one Store execution."""

    state_start: Any
    state_end: Any
    revision_start: int
    revision_end: int
    transition_count: int
    reconstructable: bool
    sequence_start: int = 0
    sequence_end: int = 0


class StoreEvidenceTracker:
    """Retain full-policy transition facts independently from OpenTelemetry export."""

    def __init__(self) -> None:
        self._revision = 0
        self._sequence = 0
        self._transitions: deque[StoreTransitionEvidence] = deque()
        self._boundaries: set[StoreBoundary] = set()

    @property
    def revision(self) -> int:
        return self._revision

    def begin(self, projection: Any) -> StoreBoundary:
        boundary = StoreBoundary(copy.deepcopy(projection), self._revision, self._sequence)
        self._boundaries.add(boundary)
        return boundary

    def release(self, boundary: StoreBoundary) -> None:
        """Release only replay history no active invocation can still need."""
        self._boundaries.discard(boundary)
        first = min((item.sequence for item in self._boundaries), default=self._sequence)
        while self._transitions and self._transitions[0].sequence <= first:
            self._transitions.popleft()

    def checkpoint(self, projection: Any) -> StoreOwnerEvidence:
        """Inspect the current state without retaining an execution history."""
        return StoreOwnerEvidence(
            state_start=copy.deepcopy(projection),
            state_end=copy.deepcopy(projection),
            revision_start=self._revision,
            revision_end=self._revision,
            transition_count=0,
            reconstructable=True,
            sequence_start=self._sequence,
            sequence_end=self._sequence,
        )

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
            sequence=self._sequence + 1,
            revision_before=revision_before,
            revision_after=revision_after,
            patch=tuple(copy.deepcopy(raw_patch)),
        )
        # ``patch_json`` must remain an exact deterministic projection of the
        # value proven portable before mutation.
        if transition.patch_json != encoded_patch:
            raise ValueError("Store transition patch encoding was not deterministic.")
        self._revision = revision_after
        self._sequence = transition.sequence
        if self._boundaries:
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

    def finalize(self, state_end: Any, boundary: StoreBoundary) -> StoreOwnerEvidence:
        end = copy.deepcopy(state_end)
        replay = copy.deepcopy(boundary.state)
        expected_revision = boundary.revision
        reconstructable = True
        transitions = (item for item in self._transitions if item.sequence > boundary.sequence)
        expected_sequence = boundary.sequence
        for expected_sequence, transition in enumerate(transitions, start=boundary.sequence + 1):
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
        if expected_sequence != self._sequence or expected_revision != self._revision or replay != end:
            reconstructable = False
        return StoreOwnerEvidence(
            state_start=copy.deepcopy(boundary.state),
            state_end=end,
            revision_start=boundary.revision,
            revision_end=self._revision,
            transition_count=self._sequence - boundary.sequence,
            sequence_start=boundary.sequence,
            sequence_end=self._sequence,
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
