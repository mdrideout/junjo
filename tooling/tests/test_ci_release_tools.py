"""Offline tests for CI routing and Studio mirror publication tooling."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPOSITORY_ROOT / "tooling" / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))


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


release_policy = load_script_module(
    "validate_studio_release_policy",
    "tooling/scripts/validate_studio_release_policy.py",
)
publisher = load_script_module(
    "publish_studio_distribution",
    "tooling/scripts/publish_studio_distribution.py",
)


class StudioReleasePolicyTests(unittest.TestCase):
    """Prove release admission is forward-only and globally unambiguous."""

    def setUp(self) -> None:
        self.contract = release_policy.load_release_contract()
        self.source_revision = "a" * 40

    def validate(self, **overrides: object) -> dict[str, str]:
        arguments: dict[str, object] = {
            "contract": self.contract,
            "studio_version": "0.81.2",
            "mode": "production",
            "release_tag": "studio-v0.81.2",
            "source_revision": self.source_revision,
            "source_is_on_master": True,
            "existing_releases": [],
            "existing_tags": ["studio-v0.81.1", "studio-v0.81.2"],
        }
        arguments.update(overrides)
        return release_policy.validate_release_policy(**arguments)

    def test_first_monorepo_release_is_admitted(self) -> None:
        self.assertEqual(
            self.validate(),
            {
                "version": "0.81.2",
                "major_minor": "0.81",
                "source_revision": self.source_revision,
                "production": "true",
                "release_state": "new",
            },
        )

    def test_exact_imported_two_part_tags_are_historical_provenance(self) -> None:
        imported_tags = [
            "studio-v0.10",
            "studio-v0.20",
            "studio-v0.30",
            "studio-v0.40",
            "studio-v0.42",
        ]
        self.assertEqual(self.contract["imported_two_part_studio_tags"], imported_tags)
        outputs = self.validate(
            existing_tags=[
                *imported_tags,
                "studio-v0.44.0",
                "studio-v0.81.1",
                "studio-v0.81.2",
            ]
        )
        self.assertEqual(outputs["release_state"], "new")

    def test_unknown_two_part_studio_tag_is_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "must be a stable X.Y.Z version"):
            self.validate(
                existing_tags=[
                    *self.contract["imported_two_part_studio_tags"],
                    "studio-v0.43",
                    "studio-v0.81.2",
                ]
            )

    def test_completed_baseline_cannot_be_rebuilt(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError, "greater than completed baseline 0.81.1"
        ):
            self.validate(
                studio_version="0.81.1",
                release_tag="studio-v0.81.1",
            )

    def test_candidate_must_be_newer_than_every_completed_release(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError, "latest completed release or stable tag 0.82.0"
        ):
            self.validate(
                existing_releases=[
                    {
                        "tagName": "studio-v0.82.0",
                        "isDraft": False,
                        "isPrerelease": False,
                    }
                ]
            )

    def test_existing_candidate_release_blocks_before_publication(self) -> None:
        for draft in (False, True):
            with self.subTest(draft=draft):
                with self.assertRaisesRegex(RuntimeError, "already exists"):
                    self.validate(
                        existing_releases=[
                            {
                                "tagName": "studio-v0.81.2",
                                "isDraft": draft,
                                "isPrerelease": False,
                            }
                        ]
                    )

    def test_newer_fetched_tag_blocks_a_queued_older_release(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError, "latest completed release or stable tag 0.81.3"
        ):
            self.validate(
                existing_tags=[
                    "studio-v0.81.1",
                    "studio-v0.81.2",
                    "studio-v0.81.3",
                ]
            )

    def test_production_source_must_be_reachable_from_master(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "reachable from origin/master"):
            self.validate(source_is_on_master=False)
        with self.assertRaisesRegex(RuntimeError, "release tag must be studio-v0.81.2"):
            self.validate(release_tag="studio-v0.81.3")

    def test_dry_run_can_validate_a_branch_without_a_release_tag(self) -> None:
        outputs = self.validate(
            mode="dry-run",
            release_tag=None,
            source_is_on_master=False,
        )
        self.assertEqual(outputs["production"], "false")

    def test_admission_classifies_completed_and_stale_states(self) -> None:
        completed = release_policy.classify_release_admission(
            contract=self.contract,
            studio_version="0.81.2",
            mode="production",
            release_tag="studio-v0.81.2",
            source_revision=self.source_revision,
            source_is_on_master=True,
            existing_releases=[
                {
                    "tagName": "studio-v0.81.2",
                    "isDraft": False,
                    "isPrerelease": False,
                }
            ],
            existing_tags=["studio-v0.81.1", "studio-v0.81.2"],
        )
        self.assertEqual(completed.state, "completed")

        stale = release_policy.classify_release_admission(
            contract=self.contract,
            studio_version="0.81.2",
            mode="production",
            release_tag="studio-v0.81.2",
            source_revision=self.source_revision,
            source_is_on_master=False,
            existing_releases=[],
            existing_tags=["studio-v0.81.1", "studio-v0.81.2"],
        )
        self.assertEqual(stale.state, "stale")

    def immutable_state(
        self, *, observed: dict[tuple[str, str], str] | None = None
    ) -> dict[str, object]:
        digest = "sha256:" + ("b" * 64)
        observed = observed or {}
        return {
            "schema_version": 1,
            "studio_version": "0.81.2",
            "source_revision": self.source_revision,
            "images": {
                service: {
                    "repository": self.contract["images"][service]["repository"],
                    "candidate_digest": digest,
                    "tags": {
                        role: observed.get((service, role))
                        for role in ("version", "source_revision")
                    },
                }
                for service in release_policy.EXPECTED_SERVICES
            },
        }

    def test_immutable_tags_classify_new_and_true_partial_resume(self) -> None:
        new = release_policy.classify_immutable_image_state(
            contract=self.contract, state=self.immutable_state()
        )
        self.assertEqual(new.state, "new")

        digest = "sha256:" + ("b" * 64)
        resume = release_policy.classify_immutable_image_state(
            contract=self.contract,
            state=self.immutable_state(
                observed={
                    ("backend", "version"): digest,
                    ("frontend", "source_revision"): digest,
                }
            ),
        )
        self.assertEqual(resume.state, "resume")

    def test_immutable_tag_digest_mismatch_is_stale(self) -> None:
        stale = release_policy.classify_immutable_image_state(
            contract=self.contract,
            state=self.immutable_state(
                observed={
                    ("backend", "version"): "sha256:" + ("c" * 64),
                }
            ),
        )
        self.assertEqual(stale.state, "stale")
        self.assertIn("backend:version", stale.reason)

    def test_release_contract_owns_exact_destinations(self) -> None:
        self.assertEqual(
            self.contract["dockerhub_immutable_tag_rules"],
            [r"^[0-9]+\.[0-9]+\.[0-9]+$", r"^[0-9a-f]{40}$"],
        )
        self.assertEqual(
            self.contract["images"]["backend"]["repository"],
            "mdrideout/junjo-ai-studio-backend",
        )
        self.assertEqual(
            self.contract["distributions"]["minimal"],
            {
                "canonical_source_path": "apps/studio/deployments/minimal",
                "mirror_repository": "mdrideout/junjo-ai-studio-minimal-build",
                "mirror_branch": "master",
            },
        )

    def test_dockerhub_controls_require_exact_live_rules_for_every_image(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="junjo-dockerhub-settings-"
        ) as temporary:
            settings_directory = Path(temporary)
            expected_rules = self.contract["dockerhub_immutable_tag_rules"]
            for service in release_policy.EXPECTED_SERVICES:
                namespace, name = self.contract["images"][service]["repository"].split(
                    "/", maxsplit=1
                )
                (settings_directory / f"{service}.json").write_text(
                    json.dumps(
                        {
                            "namespace": namespace,
                            "name": name,
                            "immutable_tags_settings": {
                                "enabled": True,
                                "rules": list(reversed(expected_rules)),
                            },
                        }
                    ),
                    encoding="utf-8",
                )

            evidence = release_policy.validate_dockerhub_controls(
                contract=self.contract,
                settings_directory=settings_directory,
            )
            self.assertEqual(evidence["schema_version"], 1)
            self.assertEqual(len(evidence["repositories"]), 3)

            frontend = json.loads(
                (settings_directory / "frontend.json").read_text(encoding="utf-8")
            )
            frontend["immutable_tags_settings"]["rules"] = [".*"]
            (settings_directory / "frontend.json").write_text(
                json.dumps(frontend), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                RuntimeError, "frontend Docker Hub immutable rules"
            ):
                release_policy.validate_dockerhub_controls(
                    contract=self.contract,
                    settings_directory=settings_directory,
                )

    def test_pull_requests_are_fast_and_releases_keep_full_validation(self) -> None:
        release_workflow = (
            REPOSITORY_ROOT / ".github/workflows/studio-docker-publish.yml"
        ).read_text(encoding="utf-8")
        validation_workflow = (
            REPOSITORY_ROOT / ".github/workflows/studio-release-validation.yml"
        ).read_text(encoding="utf-8")
        platform_gate = (
            REPOSITORY_ROOT / ".github/workflows/platform-gate.yml"
        ).read_text(encoding="utf-8")
        deployment_workflow = (
            REPOSITORY_ROOT / ".github/workflows/studio-deployments.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("workflow_call:", release_workflow)
        self.assertIn("workflow_call:", validation_workflow)
        self.assertNotIn("contents: write", validation_workflow)
        self.assertIn(
            "uses: ./.github/workflows/studio-release-validation.yml",
            release_workflow,
        )
        self.assertIn("uses: ./.github/workflows/platform-integrity.yml", platform_gate)
        self.assertNotIn("name: required", platform_gate)
        self.assertNotIn("PLATFORM_RESULT", platform_gate)
        self.assertNotIn("studio-release-validation.yml", platform_gate)
        self.assertNotIn("detect_ci_changes", platform_gate)
        self.assertIn(
            "if: github.event_name == 'workflow_dispatch' || inputs.run_live_smoke",
            deployment_workflow,
        )
        self.assertIn("run_live_smoke: true", validation_workflow)
        for workflow in (
            "python-ci.yml",
            "studio-backend-tests.yml",
            "studio-frontend-tests.yml",
            "studio-proto-staleness-check.yml",
            "studio-rest-api-contract-validation.yml",
            "studio-version-sync-check.yml",
            "telemetry-contract.yml",
            "website-ci.yml",
        ):
            self.assertNotIn(workflow, platform_gate)

    def test_release_artifacts_are_stable_and_partial_reruns_fail_closed(self) -> None:
        workflow = (
            REPOSITORY_ROOT / ".github/workflows/studio-docker-publish.yml"
        ).read_text(encoding="utf-8")
        validation_workflow = (
            REPOSITORY_ROOT / ".github/workflows/studio-release-validation.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("${{ github.run_attempt }}", workflow)
        self.assertIn(
            "run_attempt: ${{ steps.attempt.outputs.run_attempt }}",
            validation_workflow,
        )
        self.assertIn(
            "candidate-${SOURCE_REVISION}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}",
            workflow,
        )
        self.assertNotRegex(
            workflow,
            r"(?:studio-digest|studio-image-evidence|studio-distributions)-[^\n]*run_attempt",
        )
        self.assertEqual(workflow.count("overwrite: true"), 4)
        self.assertIn("--evidence-directory /tmp/studio-h2-evidence/registry", workflow)
        self.assertIn("studio-exact-agent-proof", workflow)

        production_jobs = (
            "dockerhub_controls",
            "build_architecture_images",
            "exact_manifests",
            "smoke_exact_release",
            "publish_distributions",
            "promote_floating_tags",
            "publish_release",
        )
        for job in production_jobs:
            match = re.search(
                rf"(?ms)^  {job}:\n(?P<body>.*?)(?=^  [a-z][a-z0-9_]*:\n|\Z)",
                workflow,
            )
            self.assertIsNotNone(match, f"missing production job {job}")
            body = match.group("body") if match is not None else ""
            self.assertIn("Reject partial production rerun", body)
            self.assertIn(
                "ADMITTED_RUN_ATTEMPT: ${{ needs.validation.outputs.run_attempt }}",
                body,
            )
            self.assertIn(
                'if [ "$ADMITTED_RUN_ATTEMPT" != "$GITHUB_RUN_ATTEMPT" ]',
                body,
            )

    def test_release_controls_precede_every_production_mutation(self) -> None:
        workflow = (
            REPOSITORY_ROOT / ".github/workflows/studio-docker-publish.yml"
        ).read_text(encoding="utf-8")
        self.assertLess(
            workflow.index("Validate live Docker Hub immutable-tag controls"),
            workflow.index("Build and push architecture image by digest"),
        )

        mirror_preflight = workflow.index(
            "Validate all mirror destinations before minting mutation credentials"
        )
        token = workflow.index("Create mirror installation token")
        authorized_preflight = workflow.index(
            "Revalidate all mirror destinations with the installation token"
        )
        first_publish = workflow.index(
            "publish \\\n            --export-directory /tmp/junjo-release/minimal"
        )
        self.assertLess(mirror_preflight, token)
        self.assertLess(token, authorized_preflight)
        self.assertLess(authorized_preflight, first_publish)

        evidence_upload = workflow[
            workflow.index(
                "- name: Upload release and mirror evidence"
            ) : workflow.index("\n  promote_floating_tags:")
        ]
        self.assertNotIn("/tmp/junjo-release/*.json", evidence_upload)
        for filename in (
            "minimal-export.json",
            "minimal-mirror.json",
            "vm-caddy-export.json",
            "vm-caddy-mirror.json",
        ):
            self.assertIn(f"/tmp/junjo-release/{filename}", evidence_upload)
        self.assertNotIn("mirror-preflight.json", evidence_upload)
        self.assertNotIn("mirror-authorized-preflight.json", evidence_upload)

    def test_floating_tag_verification_waits_for_registry_convergence(self) -> None:
        workflow = (
            REPOSITORY_ROOT / ".github/workflows/studio-docker-publish.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("for attempt in $(seq 1 15)", workflow)
        self.assertIn('if [ "$PROMOTED_DIGEST" = "$VERSION_DIGEST" ]; then', workflow)
        self.assertIn("sleep 2", workflow)

    def test_immutable_tag_publication_retries_transient_registry_failures(
        self,
    ) -> None:
        workflow = (
            REPOSITORY_ROOT / ".github/workflows/studio-docker-publish.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "Waiting for immutable tag $IMAGE:$tag to publish (attempt $attempt/15).",
            workflow,
        )
        self.assertIn(
            "Could not publish immutable tag $IMAGE:$tag after 15 attempts.", workflow
        )
        self.assertIn(
            'if [ "$PUBLISHED_DIGEST" != "$CANDIDATE_DIGEST" ]; then', workflow
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
            "source": {
                "distribution": "minimal",
                "canonical_source_path": "apps/studio/deployments/minimal",
                "source_revision": self.source_revision,
            },
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
                    distribution="minimal",
                    source_revision="d" * 40,
                )
        mocked_run.assert_not_called()

    def test_distribution_binding_mismatch_stops_before_authentication(self) -> None:
        manifest_path = self.export / "EXPORT_MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["source"]["distribution"] = "vm-caddy"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": self.secret}),
            mock.patch.object(publisher, "run") as mocked_run,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "export distribution does not match"
            ):
                publisher.publish(
                    export_directory=self.export,
                    distribution="minimal",
                    source_revision=self.source_revision,
                )
        mocked_run.assert_not_called()

    def test_repository_redirect_stops_before_authentication_or_clone(self) -> None:
        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": self.secret}),
            mock.patch.object(
                publisher,
                "run",
                return_value=json.dumps(
                    {
                        "full_name": "mdrideout/unexpected-mirror",
                        "default_branch": "master",
                    }
                ),
            ) as mocked_run,
        ):
            with self.assertRaisesRegex(RuntimeError, "resolved a different mirror"):
                publisher.publish(
                    export_directory=self.export,
                    distribution="minimal",
                    source_revision=self.source_revision,
                )
        mocked_run.assert_called_once_with(
            [
                "gh",
                "api",
                "repos/mdrideout/junjo-ai-studio-minimal-build",
                "--jq",
                "{full_name: .full_name, default_branch: .default_branch}",
            ]
        )

    def test_wrong_default_branch_stops_before_authentication_or_clone(self) -> None:
        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": self.secret}),
            mock.patch.object(
                publisher,
                "run",
                return_value=json.dumps(
                    {
                        "full_name": "mdrideout/junjo-ai-studio-minimal-build",
                        "default_branch": "main",
                    }
                ),
            ) as mocked_run,
        ):
            with self.assertRaisesRegex(RuntimeError, "default branch for minimal"):
                publisher.publish(
                    export_directory=self.export,
                    distribution="minimal",
                    source_revision=self.source_revision,
                )
        self.assertEqual(mocked_run.call_count, 1)

    def test_all_destinations_are_validated_together_before_authentication(
        self,
    ) -> None:
        responses = [
            json.dumps(
                {
                    "full_name": "mdrideout/junjo-ai-studio-minimal-build",
                    "default_branch": "master",
                }
            ),
            json.dumps(
                {
                    "full_name": "mdrideout/junjo-ai-studio-deployment-example",
                    "default_branch": "wrong",
                }
            ),
        ]
        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": self.secret}),
            mock.patch.object(publisher, "run", side_effect=responses) as mocked_run,
        ):
            with self.assertRaisesRegex(RuntimeError, "default branch for vm-caddy"):
                publisher.validate_mirror_destinations()
        self.assertEqual(mocked_run.call_count, 2)
        for call in mocked_run.call_args_list:
            self.assertEqual(call.args[0][:2], ["gh", "api"])

    def test_publication_is_deterministic_and_never_passes_token_in_commands(
        self,
    ) -> None:
        original_run = publisher.run
        observed_commands: list[list[str]] = []

        def offline_run(command: list[str], *, cwd: Path | None = None) -> str:
            observed_commands.append(command)
            if command[:2] == ["gh", "api"]:
                return json.dumps(
                    {
                        "full_name": "mdrideout/junjo-ai-studio-minimal-build",
                        "default_branch": "master",
                    }
                )
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
                distribution="minimal",
                source_revision=self.source_revision,
            )
            second = publisher.publish(
                export_directory=self.export,
                distribution="minimal",
                source_revision=self.source_revision,
            )

        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(first["commit"], second["commit"])
        self.assertEqual(first["tree_sha256"], "b" * 64)
        self.assertEqual(first["distribution"], "minimal")
        self.assertEqual(first["repository"], "mdrideout/junjo-ai-studio-minimal-build")
        self.assertEqual(first["branch"], "master")
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
