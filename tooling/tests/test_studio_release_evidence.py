"""Offline tests for deterministic Studio release evidence construction."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


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


evidence_builder = load_script_module(
    "build_studio_release_evidence",
    "tooling/scripts/build_studio_release_evidence.py",
)


class StudioReleaseEvidenceTests(unittest.TestCase):
    """Exercise release evidence validation using only local artifacts."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="junjo-release-evidence-"
        )
        self.root = Path(self.temporary_directory.name)
        self.images = self.root / "images"
        self.distributions = self.root / "distributions"
        self.images.mkdir()
        self.distributions.mkdir()
        self.contract = evidence_builder.load_release_contract()
        self.version = "0.81.2"
        self.release_tag = f"studio-v{self.version}"
        self.source_repository = "https://github.com/mdrideout/junjo"
        self.source_revision = "a" * 40
        self.workflow_url = "https://github.com/mdrideout/junjo/actions/runs/123"
        self.mirror_commits = {
            "minimal": "b" * 40,
            "vm-caddy": "c" * 40,
        }
        for service, character in zip(
            evidence_builder.SERVICES,
            ("1", "2", "3"),
            strict=True,
        ):
            digest = f"sha256:{character * 64}"
            self.write_json_to(
                self.images / f"{service}.json",
                {
                    "schema_version": 1,
                    "service": service,
                    "repository": self.contract["images"][service]["repository"],
                    "studio_version": self.version,
                    "source_revision": self.source_revision,
                    "digest": digest,
                    "tags": {
                        "version": {"name": self.version, "digest": digest},
                        "source_revision": {
                            "name": self.source_revision,
                            "digest": digest,
                        },
                    },
                },
            )
        for name in evidence_builder.DISTRIBUTIONS:
            canonical_source_path = self.contract["distributions"][name][
                "canonical_source_path"
            ]
            self.write_distribution(name, canonical_source_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_distribution(
        self,
        name: str,
        canonical_source_path: str,
        *,
        inventory: list[dict[str, object]] | None = None,
        reported_tree_sha256: str | None = None,
    ) -> None:
        """Write one internally consistent local release distribution fixture."""
        if inventory is None:
            content = b"Junjo release fixture\n"
            inventory = [
                {
                    "mode": "0644",
                    "path": "README.md",
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size": len(content),
                }
            ]
        calculated_tree_sha256 = hashlib.sha256(
            json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        tree_sha256 = reported_tree_sha256 or calculated_tree_sha256
        source = {
            "schema_version": 1,
            "distribution": name,
            "source_repository": self.source_repository,
            "canonical_source_path": canonical_source_path,
            "source_revision": self.source_revision,
            "studio_version": self.version,
            "compatible_sdk_version": "0.23.0",
        }
        manifest = {
            "schema_version": 1,
            "source": source,
            "tree_sha256": tree_sha256,
            "inventory": inventory,
        }
        manifest_content = (
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        archive_name = f"junjo-ai-studio-{name}-{self.version}.tar.gz"
        archive = self.distributions / archive_name
        with tarfile.open(archive, mode="w:gz") as release_archive:
            readme_content = b"Junjo release fixture\n"
            readme = tarfile.TarInfo(f"junjo-ai-studio-{name}-{self.version}/README.md")
            readme.mode = 0o644
            readme.size = len(readme_content)
            release_archive.addfile(readme, io.BytesIO(readme_content))
            member = tarfile.TarInfo(
                f"junjo-ai-studio-{name}-{self.version}/EXPORT_MANIFEST.json"
            )
            member.size = len(manifest_content)
            release_archive.addfile(member, io.BytesIO(manifest_content))

        export_report = {
            "distribution": name,
            "archive": f"/tmp/junjo-release/{archive_name}",
            "archive_sha256": evidence_builder.sha256_file(archive),
            "tree_sha256": tree_sha256,
            "source": source,
        }
        self.write_json(f"{name}-export.json", export_report)
        self.write_json(
            f"{name}-mirror.json",
            {
                "distribution": name,
                "repository": self.contract["distributions"][name]["mirror_repository"],
                "branch": self.contract["distributions"][name]["mirror_branch"],
                "commit": self.mirror_commits[name],
                "source_revision": self.source_revision,
                "changed": True,
                "tree_sha256": tree_sha256,
            },
        )

    def write_json(self, filename: str, value: object) -> None:
        self.write_json_to(self.distributions / filename, value)

    def write_json_to(self, path: Path, value: object) -> None:
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def read_json(self, filename: str) -> dict[str, object]:
        return json.loads((self.distributions / filename).read_text(encoding="utf-8"))

    def build(self, **overrides: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "studio_version": self.version,
            "release_tag": self.release_tag,
            "source_repository": self.source_repository,
            "source_revision": self.source_revision,
            "workflow_url": self.workflow_url,
            "image_directory": self.images,
            "distribution_directory": self.distributions,
        }
        arguments.update(overrides)
        return evidence_builder.build_release_evidence(**arguments)

    def test_builds_complete_deterministic_evidence_and_notes(self) -> None:
        first = self.build()
        second = self.build()

        self.assertEqual(first, second)
        self.assertEqual(first["release_tag"], self.release_tag)
        self.assertEqual(
            list(first["images"]),
            list(evidence_builder.SERVICES),
        )
        self.assertEqual(
            list(first["distributions"]),
            list(evidence_builder.DISTRIBUTIONS),
        )
        self.assertEqual(
            evidence_builder.build_release_notes(first),
            evidence_builder.build_release_notes(second),
        )

    def test_requires_exact_tag_for_studio_version(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "release tag must be"):
            self.build(release_tag="studio-v0.81.3")

    def test_rejects_pre_monorepo_baseline(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "greater than completed baseline"):
            self.build(studio_version="0.81.1", release_tag="studio-v0.81.1")

    def test_requires_full_source_revision(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "source revision must be"):
            self.build(source_revision="abc123")

    def test_rejects_invalid_image_digest(self) -> None:
        report = json.loads((self.images / "frontend.json").read_text())
        report["digest"] = "sha256:not-a-digest"
        self.write_json_to(self.images / "frontend.json", report)
        with self.assertRaisesRegex(RuntimeError, "frontend image digest"):
            self.build()

    def test_rejects_unexpected_evidence_files(self) -> None:
        (self.images / "stale.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(
            RuntimeError, "image evidence files must be exactly"
        ):
            self.build()

    def test_rejects_wrong_image_repository(self) -> None:
        report = json.loads((self.images / "backend.json").read_text())
        report["repository"] = "someone/else"
        self.write_json_to(self.images / "backend.json", report)
        with self.assertRaisesRegex(RuntimeError, "repository does not match"):
            self.build()

    def test_rejects_immutable_tag_digest_mismatch(self) -> None:
        report = json.loads((self.images / "ingestion.json").read_text())
        report["tags"]["source_revision"]["digest"] = "sha256:" + "f" * 64
        self.write_json_to(self.images / "ingestion.json", report)
        with self.assertRaisesRegex(RuntimeError, "does not resolve"):
            self.build()

    def test_rejects_export_source_revision_mismatch(self) -> None:
        report = self.read_json("minimal-export.json")
        report["source"]["source_revision"] = "d" * 40
        self.write_json("minimal-export.json", report)
        with self.assertRaisesRegex(RuntimeError, "source source_revision"):
            self.build()

    def test_rejects_archive_content_mismatch(self) -> None:
        archive = self.distributions / f"junjo-ai-studio-minimal-{self.version}.tar.gz"
        with archive.open("ab") as output:
            output.write(b"tampered")
        with self.assertRaisesRegex(RuntimeError, "archive content"):
            self.build()

    def test_rejects_tree_hash_that_does_not_match_inventory(self) -> None:
        self.write_distribution(
            "minimal",
            self.contract["distributions"]["minimal"]["canonical_source_path"],
            reported_tree_sha256="d" * 64,
        )
        with self.assertRaisesRegex(RuntimeError, "inventory does not match"):
            self.build()

    def test_records_the_validated_mirror_report_commit(self) -> None:
        report = self.read_json("vm-caddy-mirror.json")
        report["commit"] = "d" * 40
        self.write_json("vm-caddy-mirror.json", report)
        evidence = self.build()
        self.assertEqual(
            evidence["distributions"]["vm-caddy"]["mirror"]["commit"],
            "d" * 40,
        )

    def test_rejects_invalid_mirror_commit_sha(self) -> None:
        report = self.read_json("minimal-mirror.json")
        report["commit"] = "not-a-sha"
        self.write_json("minimal-mirror.json", report)
        with self.assertRaisesRegex(RuntimeError, "mirror commit must be"):
            self.build()

    def test_rejects_wrong_mirror_repository_or_branch(self) -> None:
        for key, value in (("repository", "someone/else"), ("branch", "other")):
            with self.subTest(key=key):
                report = self.read_json("minimal-mirror.json")
                original = report[key]
                report[key] = value
                self.write_json("minimal-mirror.json", report)
                with self.assertRaisesRegex(
                    RuntimeError, f"mirror {key} does not match"
                ):
                    self.build()
                report[key] = original
                self.write_json("minimal-mirror.json", report)


if __name__ == "__main__":
    unittest.main()
