"""Offline tests for CI routing and Studio mirror publication tooling."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def load_script_module(name: str, relative_path: str) -> ModuleType:
    """Load a repository script without making ``tooling`` a package."""
    path = REPOSITORY_ROOT / relative_path
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


detector = load_script_module(
    "detect_ci_changes",
    "tooling/scripts/detect_ci_changes.py",
)
publisher = load_script_module(
    "publish_studio_distribution",
    "tooling/scripts/publish_studio_distribution.py",
)


class ChangeDetectionTests(unittest.TestCase):
    """Prove repository paths select the checks that own those paths."""

    def enabled_components(self, *paths: str) -> set[str]:
        result = detector.detect_components(paths)
        return {name for name, enabled in result.items() if enabled}

    def test_shared_telemetry_contract_fans_out_to_producers_and_consumers(
        self,
    ) -> None:
        self.assertEqual(
            self.enabled_components("contracts/telemetry/spans/v1/schema.json"),
            {"python", "studio_backend", "studio_frontend", "telemetry"},
        )

    def test_component_local_paths_do_not_enable_unrelated_checks(self) -> None:
        cases = {
            "sdks/python/docs/index.rst": {"python"},
            "apps/studio/backend/tests/test_health.py": {"studio_backend"},
            "apps/studio/frontend/src/App.tsx": {"studio_frontend"},
            "apps/studio/deployments/minimal/docker-compose.yml": {"deployments"},
            "apps/website/src/content/docs/index.mdx": {"website"},
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(self.enabled_components(path), expected)

    def test_run_all_paths_enable_every_component(self) -> None:
        for path in detector.RUN_ALL_PATHS:
            with self.subTest(path=path):
                self.assertEqual(
                    self.enabled_components(path),
                    set(detector.COMPONENTS),
                )

    def test_platform_gate_path_with_dot_slash_still_runs_every_check(self) -> None:
        self.assertEqual(
            self.enabled_components("./.github/workflows/platform-gate.yml"),
            set(detector.COMPONENTS),
        )

    def test_shared_local_action_change_runs_every_check(self) -> None:
        self.assertEqual(
            self.enabled_components(".github/actions/setup-platform/action.yml"),
            set(detector.COMPONENTS),
        )

    def test_any_workflow_change_runs_every_check(self) -> None:
        self.assertEqual(
            self.enabled_components(".github/workflows/studio-docker-publish.yml"),
            set(detector.COMPONENTS),
        )

    def test_deployment_publication_tooling_runs_deployment_checks(self) -> None:
        paths = (
            "tooling/scripts/build_studio_release_evidence.py",
            "tooling/scripts/publish_studio_distribution.py",
            "tooling/tests/test_studio_deployment_tools.py",
            "tooling/tests/test_studio_release_evidence.py",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.enabled_components(path), {"deployments"})

    def test_main_appends_stable_github_outputs_in_component_order(self) -> None:
        with tempfile.TemporaryDirectory(prefix="junjo-ci-output-") as temporary:
            output_path = Path(temporary) / "github-output"
            arguments = [
                "detect_ci_changes.py",
                "apps/website/package.json",
                "--github-output",
                str(output_path),
            ]
            with mock.patch.object(sys, "argv", arguments):
                detector.main()

            expected = [
                f"{component}={'true' if component == 'website' else 'false'}"
                for component in detector.COMPONENTS
            ]
            self.assertEqual(
                output_path.read_text(encoding="utf-8").splitlines(),
                expected,
            )


class MirrorTreeTests(unittest.TestCase):
    """Prove publication compares the complete generated mirror tree."""

    def test_equal_trees_accept_identical_files_and_reject_inventory_drift(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="junjo-tree-equality-") as temporary:
            root = Path(temporary)
            expected = root / "expected"
            actual = root / "actual"
            for directory in (expected, actual):
                (directory / "scripts").mkdir(parents=True)
                (directory / "README.md").write_text("same\n", encoding="utf-8")
                (directory / "scripts" / "junjo").write_text(
                    "#!/usr/bin/env python3\n", encoding="utf-8"
                )

            publisher.require_equal_trees(expected, actual)
            (actual / "unexpected.txt").write_text("drift\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "mirror inventory differs"):
                publisher.require_equal_trees(expected, actual)

    def test_equal_trees_reject_content_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="junjo-tree-content-") as temporary:
            root = Path(temporary)
            expected = root / "expected"
            actual = root / "actual"
            expected.mkdir()
            actual.mkdir()
            (expected / "README.md").write_text("expected\n", encoding="utf-8")
            (actual / "README.md").write_text("changed\n", encoding="utf-8")

            with self.assertRaisesRegex(
                RuntimeError, "mirror content differs: README.md"
            ):
                publisher.require_equal_trees(expected, actual)

    def test_equal_trees_reject_executable_mode_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="junjo-tree-mode-") as temporary:
            root = Path(temporary)
            expected = root / "expected"
            actual = root / "actual"
            expected.mkdir()
            actual.mkdir()
            for directory in (expected, actual):
                script = directory / "junjo"
                script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            (expected / "junjo").chmod(0o755)
            (actual / "junjo").chmod(0o644)

            with self.assertRaisesRegex(RuntimeError, "mirror mode differs: junjo"):
                publisher.require_equal_trees(expected, actual)


class MirrorPublicationTests(unittest.TestCase):
    """Exercise mirror publication against local Git repositories only."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="junjo-mirror-publication-"
        )
        self.root = Path(self.temporary_directory.name)
        self.remote = self.root / "mirror.git"
        self.seed = self.root / "seed"
        self.export = self.root / "export"
        self.source_revision = "a" * 40
        self.secret = "never-print-this-token"

        self.git("init", "--bare", "--initial-branch=master", str(self.remote))
        self.git("init", "--initial-branch=master", str(self.seed))
        self.git("config", "user.name", "Junjo Test", cwd=self.seed)
        self.git("config", "user.email", "junjo-test@example.invalid", cwd=self.seed)
        (self.seed / "obsolete.txt").write_text("remove me\n", encoding="utf-8")
        self.git("add", ".", cwd=self.seed)
        self.git("commit", "--quiet", "-m", "seed mirror", cwd=self.seed)
        self.git("remote", "add", "origin", str(self.remote), cwd=self.seed)
        self.git("push", "--quiet", "origin", "master", cwd=self.seed)

        self.export.mkdir()
        (self.export / "LICENSE").write_text("Apache License 2.0\n", encoding="utf-8")
        (self.export / "README.md").write_text("Generated mirror\n", encoding="utf-8")
        manifest = {
            "source": {"source_revision": self.source_revision},
            "tree_sha256": "b" * 64,
        }
        (self.export / "EXPORT_MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def git(self, *arguments: str, cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def test_manifest_revision_mismatch_stops_before_clone(self) -> None:
        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": self.secret}),
            mock.patch.object(publisher, "run") as mocked_run,
        ):
            with self.assertRaisesRegex(RuntimeError, "source revision does not match"):
                publisher.publish(
                    export_directory=self.export,
                    repository="mdrideout/generated-mirror",
                    branch="master",
                    source_revision="different-revision",
                )
        mocked_run.assert_not_called()

    def test_publication_is_deterministic_and_never_passes_token_in_commands(
        self,
    ) -> None:
        original_run = publisher.run
        observed_commands: list[list[str]] = []

        def offline_run(command: list[str], *, cwd: Path | None = None) -> str:
            observed_commands.append(command)
            if command == ["gh", "auth", "setup-git"]:
                return ""
            if command[:3] == ["gh", "repo", "clone"]:
                destination = Path(command[4])
                branch = command[7]
                self.git(
                    "clone",
                    "--quiet",
                    "--branch",
                    branch,
                    str(self.remote),
                    str(destination),
                )
                return ""
            return original_run(command, cwd=cwd)

        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": self.secret}),
            mock.patch.object(publisher, "run", side_effect=offline_run),
        ):
            first = publisher.publish(
                export_directory=self.export,
                repository="mdrideout/generated-mirror",
                branch="master",
                source_revision=self.source_revision,
            )
            second = publisher.publish(
                export_directory=self.export,
                repository="mdrideout/generated-mirror",
                branch="master",
                source_revision=self.source_revision,
            )

        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(first["commit"], second["commit"])
        self.assertEqual(first["tree_sha256"], "b" * 64)
        evidence = json.dumps([first, second, observed_commands], sort_keys=True)
        self.assertNotIn(self.secret, evidence)
        auth_indexes = [
            index
            for index, command in enumerate(observed_commands)
            if command == ["gh", "auth", "setup-git"]
        ]
        clone_indexes = [
            index
            for index, command in enumerate(observed_commands)
            if command[:3] == ["gh", "repo", "clone"]
        ]
        self.assertEqual(len(auth_indexes), 2)
        self.assertEqual(len(clone_indexes), 4)
        self.assertLess(auth_indexes[0], clone_indexes[0])
        self.assertLess(auth_indexes[1], clone_indexes[2])


if __name__ == "__main__":
    unittest.main()
