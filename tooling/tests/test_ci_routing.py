"""Focused tests for explicit monorepo CI path ownership."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def load_detector() -> ModuleType:
    """Load the dependency-free detector without making tooling a package."""
    path = REPOSITORY_ROOT / "tooling/scripts/detect_ci_changes.py"
    specification = importlib.util.spec_from_file_location("ci_routing_detector", path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


detector = load_detector()


class StudioRootRoutingTests(unittest.TestCase):
    """Prove cross-service Studio inputs select every affected owner."""

    def enabled(self, path: str) -> set[str]:
        return {
            component
            for component, selected in detector.detect_components([path]).items()
            if selected
        }

    def test_root_container_context_routes_all_image_consumers(self) -> None:
        self.assertEqual(
            self.enabled("apps/studio/.dockerignore"),
            {"studio_backend", "studio_frontend", "telemetry", "deployments"},
        )

    def test_compose_and_setup_inputs_route_runtime_and_deployments(self) -> None:
        expected = {"studio_backend", "studio_frontend", "telemetry", "deployments"}
        for path in (
            "apps/studio/.env.example",
            "apps/studio/compose.yaml",
            "apps/studio/compose.monitoring.yaml",
            "apps/studio/scripts/junjo",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.enabled(path), expected)

    def test_e2e_app_routes_telemetry_and_deployment_proof(self) -> None:
        self.assertEqual(
            self.enabled("apps/studio/e2e_test_apps/app/main.py"),
            {"telemetry", "deployments"},
        )

    def test_release_and_smoke_tooling_routes_deployment_proof(self) -> None:
        for path in (
            "tooling/studio_release_contract.json",
            "tooling/scripts/validate_studio_release_policy.py",
            "tooling/scripts/smoke_studio_distribution.py",
            "tooling/scripts/validate_studio_runtime.py",
            "tooling/tests/test_studio_runtime.py",
            "tooling/tests/test_studio_setup_wizards.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.enabled(path), {"deployments"})

    def test_service_dockerfiles_route_deployment_smoke(self) -> None:
        expected = {
            "apps/studio/backend/Dockerfile": {"studio_backend", "deployments"},
            "apps/studio/frontend/Dockerfile": {"studio_frontend", "deployments"},
            "apps/studio/ingestion/Dockerfile": {
                "studio_backend",
                "telemetry",
                "deployments",
            },
        }
        for path, components in expected.items():
            with self.subTest(path=path):
                self.assertEqual(self.enabled(path), components)

    def test_studio_artifact_license_inputs_route_every_image_owner(self) -> None:
        expected = {
            "studio_backend",
            "studio_frontend",
            "telemetry",
            "deployments",
        }
        for path in (
            "apps/studio/LICENSE",
            "apps/studio/THIRD_PARTY_NOTICES.md",
            "apps/studio/licenses/artifact-license-policy.json",
            "apps/studio/licenses/frontend-production.json",
            "apps/studio/licenses/ingestion-production.json",
            "tooling/scripts/validate_studio_artifact_licenses.py",
            "tooling/tests/test_studio_artifact_licenses.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.enabled(path), expected)

    def test_new_unowned_studio_runtime_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "has no CI owner"):
            detector.detect_components(["apps/studio/new_runtime/worker.py"])

    def test_documentation_path_does_not_claim_runtime_ownership(self) -> None:
        self.assertEqual(
            self.enabled("apps/studio/docs/adr/006-studio-release-transaction.md"),
            set(),
        )


if __name__ == "__main__":
    unittest.main()
