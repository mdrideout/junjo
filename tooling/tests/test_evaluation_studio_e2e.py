"""Offline contract tests for the installed evaluation-to-Studio validator."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPOSITORY_ROOT / "tooling/scripts"


def load_validator() -> ModuleType:
    """Load the standalone tooling script without making tooling a package."""

    sys.path.insert(0, str(SCRIPTS_ROOT))
    path = SCRIPTS_ROOT / "validate_evaluation_studio_e2e.py"
    specification = importlib.util.spec_from_file_location(
        "validate_evaluation_studio_e2e",
        path,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


validator = load_validator()


def attempt_evidence() -> dict[str, object]:
    """Return one complete bounded evaluation evidence fixture."""

    return {
        "attempt": {
            "attempt": {
                "id": "attempt-1",
                "status": "passed",
                "subject_evidence": {
                    "service_namespace": validator.SERVICE_NAMESPACE,
                    "service_name": validator.SERVICE_NAME,
                    "executable_type": "workflow",
                    "runtime_id": "runtime-1",
                },
            }
        },
        "resolution": {
            "service_namespace": validator.SERVICE_NAMESPACE,
            "service_name": validator.SERVICE_NAME,
            "runtime_id": "runtime-1",
        },
        "evidence": {
            "spans": [
                {
                    "attributes_json": {
                        "junjo.evaluation.run.id": "run-1",
                        "junjo.evaluation.attempt.id": "attempt-1",
                        "junjo.evaluation.run_class": "evaluation",
                        "junjo.evaluation.role": role,
                    },
                    "resource_attributes_json": {
                        "service.namespace": validator.SERVICE_NAMESPACE,
                        "service.name": validator.SERVICE_NAME,
                    },
                }
                for role in ("orchestrator", "subject")
            ]
        },
    }


class EvaluationStudioE2EToolingTests(unittest.TestCase):
    """Prove credential and evidence validation fails closed offline."""

    def test_attempt_evidence_requires_bounded_roles_and_real_service_identity(
        self,
    ) -> None:
        evidence = attempt_evidence()
        validator.assert_attempt_evidence(
            evidence,
            attempt_id="attempt-1",
            run_id="run-1",
            expected_status="passed",
        )

        evidence["evidence"]["spans"].pop()
        with self.assertRaisesRegex(
            validator.StudioE2EError,
            "orchestration or subject",
        ):
            validator.assert_attempt_evidence(
                evidence,
                attempt_id="attempt-1",
                run_id="run-1",
                expected_status="passed",
            )

    def test_command_data_rejects_unsuccessful_or_non_object_payloads(self) -> None:
        with self.assertRaisesRegex(
            validator.StudioE2EError,
            "did not succeed",
        ):
            validator.command_data({"ok": False, "data": {}})
        with self.assertRaisesRegex(
            validator.StudioE2EError,
            "must be an object",
        ):
            validator.command_data({"ok": True, "data": []})

    def test_attempt_evidence_accepts_the_expected_failed_outcome(self) -> None:
        evidence = attempt_evidence()
        evidence["attempt"]["attempt"]["status"] = "failed"
        validator.assert_attempt_evidence(
            evidence,
            attempt_id="attempt-1",
            run_id="run-1",
            expected_status="failed",
        )

    def test_evaluation_credential_requires_generated_token_prefix(self) -> None:
        class Client:
            def request(self, path, *, method, body):
                self.requested = (path, method, body)
                return {
                    "id": "token-1",
                    "token": "jcli_generated-token",
                }

        client = Client()
        credential = validator.create_evaluation_credential(client)

        self.assertEqual(credential.id, "token-1")
        self.assertEqual(
            client.requested,
            (
                "/api/v1/evaluation-tokens",
                "POST",
                {
                    "name": "Junjo Evaluation E2E",
                    "scopes": list(validator.EVALUATION_SCOPES),
                },
            ),
        )

    def test_evaluation_credential_deletion_uses_management_delete_route(self) -> None:
        class Client:
            def request(self, path, *, method):
                self.requested = (path, method)
                return None

        client = Client()
        credential = validator.EvaluationCredential(
            id="token-1",
            token="jcli_generated-token",
        )

        validator.delete_evaluation_credential(client, credential)

        self.assertEqual(
            client.requested,
            ("/api/v1/evaluation-tokens/token-1", "DELETE"),
        )


if __name__ == "__main__":
    unittest.main()
