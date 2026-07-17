"""Offline contract tests for the live Agent -> Studio E2E validator."""

from __future__ import annotations

import copy
import importlib.util
import sys
import tempfile
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

    def test_browser_evidence_contains_only_resolvable_execution_identity(self) -> None:
        expectations = validator.ExecutionExpectations(
            service_name="agent-proof",
            agent_runtime_id="agent-runtime",
            agent_definition_id="agent-definition",
            agent_structural_id="agent-structural",
            workflow_runtime_id="workflow-runtime",
            workflow_definition_id="workflow-definition",
            workflow_start={"value": "start"},
            workflow_end={"value": "end"},
        )
        evidence = validator.build_browser_evidence(
            summary={"agent_span_id": "a" * 16},
            expectations=expectations,
            trace_id="b" * 32,
            workflow_span_id="c" * 16,
            tool_span_id="d" * 16,
        )

        self.assertEqual(evidence["agent_run_id"], "agent-runtime")
        self.assertEqual(evidence["nested_workflow_span_id"], "c" * 16)
        self.assertNotIn("api_key", evidence)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence.json"
            validator.write_browser_evidence(output, evidence)
            self.assertIn('"service_name": "agent-proof"', output.read_text(encoding="utf-8"))

    def test_current_trace_evidence_projects_agent_and_workflow_details(self) -> None:
        summary = {
            "trace_id": "1" * 32,
            "agent_span_id": "a" * 16,
            "runtime_id": "agent-runtime",
        }
        agent_store = verified_store()
        workflow_store = verified_store()
        evidence = {
            "executables_by_span_id": {
                "a" * 16: {
                    "executable_type": "agent",
                    "runtime_id": "agent-runtime",
                    "store_id": "agent-store",
                    "unavailable_store": None,
                    "summary": summary,
                    "definition": full({"name": "agent"}),
                    "input": full({"value": "input"}),
                    "output": full({"value": "output"}),
                    "input_candidate": None,
                    "history_candidate": None,
                    "error": None,
                    "cancellation": None,
                    "integrity": {"status": "complete"},
                },
                "b" * 16: {
                    "executable_type": "workflow",
                    "runtime_id": "workflow-runtime",
                    "store_id": "workflow-store",
                    "unavailable_store": None,
                    "name": validator.WORKFLOW_NAME,
                    "integrity": {"status": "complete"},
                },
            },
            "operations_by_owner_runtime_id": {
                "agent-runtime": {
                    "c" * 16: {"sequence": 2, "span_id": "c" * 16},
                    "d" * 16: {"sequence": 1, "span_id": "d" * 16},
                }
            },
            "stores_by_id": {
                "agent-store": {
                    "owner_span_id": "a" * 16,
                    "detail": agent_store,
                },
                "workflow-store": {
                    "owner_span_id": "b" * 16,
                    "detail": workflow_store,
                },
            },
            "relationships_by_owner_span_id": {
                "a" * 16: {
                    "parent": None,
                    "nested": [{"span_id": "b" * 16}],
                }
            },
        }

        agent = validator.project_agent_detail(summary, evidence)
        workflow = validator.project_workflow_diagnostic(
            evidence,
            trace_id="1" * 32,
            workflow_span_id="b" * 16,
        )

        self.assertEqual(
            [operation["sequence"] for operation in agent["operations"]],
            [1, 2],
        )
        self.assertIs(agent["state"], agent_store)
        self.assertEqual(agent["nested_executables"], [{"span_id": "b" * 16}])
        self.assertIs(workflow["state"], workflow_store)
        self.assertEqual(workflow["executable_type"], "workflow")

    def test_identity_cleanup_stops_after_deleting_the_authenticated_user(self) -> None:
        requests: list[tuple[str, str]] = []

        class FakeClient:
            def request(
                self,
                path: str,
                *,
                method: str = "GET",
                body: object = None,
            ) -> None:
                requests.append((path, method))

        identity = validator.TestIdentity(
            email="smoke@example.com",
            password="secret",
            user_id="user-id",
            api_key_id="key-id",
            api_key="api-key",
        )
        validator.cleanup_test_identity(FakeClient(), identity)

        self.assertEqual(
            requests,
            [
                ("/api_keys/key-id", "DELETE"),
                ("/users/user-id", "DELETE"),
            ],
        )

if __name__ == "__main__":
    unittest.main()
