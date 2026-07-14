"""Offline contract tests for the live Agent -> Studio E2E validator."""

from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def load_validator() -> ModuleType:
    """Load the stdlib-only script without making tooling a package."""

    path = REPOSITORY_ROOT / "tooling/scripts/validate_agent_studio_e2e.py"
    specification = importlib.util.spec_from_file_location(
        "validate_agent_studio_e2e",
        path,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


validator = load_validator()


def full(value: object) -> dict[str, object]:
    """Build one full-policy semantic payload slot."""

    return {
        "mode": "full",
        "policy": validator.FULL_POLICY,
        "value": value,
        "reference": None,
        "reason": None,
    }


def apply_fixture_patch(
    document: object,
    patch: list[dict[str, object]],
) -> object:
    """Apply the small RFC 6902 subset used by this offline fixture."""

    result = copy.deepcopy(document)
    for operation in patch:
        if operation.get("op") == "replace" and operation.get("path") == "":
            result = copy.deepcopy(operation["value"])
            continue
        if operation.get("op") == "replace" and operation.get("path") == "/value":
            if not isinstance(result, dict):
                raise AssertionError("fixture document must be an object")
            result["value"] = copy.deepcopy(operation["value"])
            continue
        raise AssertionError(f"unsupported fixture patch: {operation}")
    return result


def verified_store() -> dict[str, object]:
    """Return one complete Store projection for replay tests."""

    first_patch = [{"op": "replace", "path": "/value", "value": "middle"}]
    second_patch = [{"op": "replace", "path": "/value", "value": "end"}]
    return {
        "available": True,
        "store_id": "store-test",
        "revision_start": 0,
        "revision_end": 2,
        "transition_count": 2,
        "reconstructable_claimed": True,
        "reconstructable": True,
        "reconstruction_status": "verified",
        "reconstruction_reason": None,
        "start": full({"value": "start"}),
        "end": full({"value": "end"}),
        "transitions": [
            {
                "sequence": 1,
                "revision_before": 0,
                "revision_after": 1,
                "span_id": "span-one",
                "event_id": "event-one",
                "action": "first",
                "patch": full(first_patch),
                "before": {"value": "start"},
                "after": {"value": "middle"},
            },
            {
                "sequence": 2,
                "revision_before": 1,
                "revision_after": 2,
                "span_id": "span-two",
                "event_id": "event-two",
                "action": "second",
                "patch": full(second_patch),
                "before": {"value": "middle"},
                "after": {"value": "end"},
            },
        ],
    }


class FakeClock:
    """Deterministic monotonic clock advanced only by the injected sleeper."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class AgentStudioE2EToolingTests(unittest.TestCase):
    """Prove polling, payload, and independent replay fail closed offline."""

    def test_bounded_poll_sleeps_only_between_unsatisfied_attempts(self) -> None:
        clock = FakeClock()
        values = iter([None, None, "ready"])
        result = validator.bounded_poll(
            lambda: next(values),
            accept=lambda value: value == "ready",
            timeout_seconds=5,
            interval_seconds=1,
            description="fixture",
            clock=clock.clock,
            sleeper=clock.sleep,
        )
        self.assertEqual(result, "ready")
        self.assertEqual(clock.sleeps, [1, 1])

    def test_bounded_poll_stops_at_its_monotonic_deadline(self) -> None:
        clock = FakeClock()
        with self.assertRaisesRegex(validator.StudioE2EError, "Timed out after 3 attempts"):
            validator.bounded_poll(
                lambda: None,
                accept=lambda value: value is not None,
                timeout_seconds=2,
                interval_seconds=1,
                description="fixture",
                clock=clock.clock,
                sleeper=clock.sleep,
            )
        self.assertEqual(clock.now, 2)
        self.assertEqual(clock.sleeps, [1, 1])

    def test_full_payload_requires_explicit_mode_policy_and_value(self) -> None:
        self.assertEqual(validator.assert_full_payload(full({"answer": 1}), "fixture"), {"answer": 1})
        with self.assertRaisesRegex(validator.StudioE2EError, "must use full mode"):
            validator.assert_full_payload(
                {
                    "mode": "redacted",
                    "policy": validator.FULL_POLICY,
                    "value": {"answer": "hidden"},
                    "reference": None,
                    "reason": None,
                },
                "fixture",
            )
        missing_value = full(None)
        del missing_value["value"]
        with self.assertRaisesRegex(validator.StudioE2EError, "must contain a value"):
            validator.assert_full_payload(missing_value, "fixture")

    def test_verified_store_is_independently_replayed(self) -> None:
        validator.assert_verified_store(
            verified_store(),
            expected_start={"value": "start"},
            expected_end={"value": "end"},
            expected_actions=["first", "second"],
            apply_patch=apply_fixture_patch,
        )

    def test_verified_store_rejects_backend_projection_or_revision_tampering(self) -> None:
        bad_after = verified_store()
        bad_after["transitions"][0]["after"] = {"value": "invented"}
        with self.assertRaisesRegex(validator.StudioE2EError, "after projection is incorrect"):
            validator.assert_verified_store(
                bad_after,
                expected_start={"value": "start"},
                expected_end={"value": "end"},
                expected_actions=["first", "second"],
                apply_patch=apply_fixture_patch,
            )

        bad_revision = verified_store()
        bad_revision["transitions"][1]["revision_before"] = 0
        with self.assertRaisesRegex(validator.StudioE2EError, "revision chain is discontinuous"):
            validator.assert_verified_store(
                bad_revision,
                expected_start={"value": "start"},
                expected_end={"value": "end"},
                expected_actions=["first", "second"],
                apply_patch=apply_fixture_patch,
            )


if __name__ == "__main__":
    unittest.main()
