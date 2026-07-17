"""Offline tests for release-selected documentation publication."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DocumentationReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(
            (REPOSITORY_ROOT / "tooling/docs/stable-releases.json").read_text(
                encoding="utf-8"
            )
        )
        self.validator = load_module(
            "validate_release_manifest",
            REPOSITORY_ROOT / "tooling/docs/validate_release_manifest.py",
        )
        self.promoter = load_module(
            "promote_production_branch",
            REPOSITORY_ROOT / "tooling/docs/promote_production_branch.py",
        )

    def test_stable_manifest_selects_versioned_component_tags(self) -> None:
        self.assertEqual(self.manifest["version"], 1)
        self.assertEqual(
            self.manifest["python"]["release_tag"],
            f"sdk-python-v{self.manifest['python']['version']}",
        )
        self.assertEqual(
            self.manifest["studio"]["release_tag"],
            f"studio-v{self.manifest['studio']['version']}",
        )
        self.assertEqual(self.manifest["python"]["content_format"], "owned-markdown")

    def test_legacy_python_release_has_an_immutable_public_surface(self) -> None:
        surface = json.loads(
            (
                REPOSITORY_ROOT
                / "tooling/docs/release-snapshots/python"
                / "0.64.0"
                / "api-public-surface.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(surface["version"], 2)
        self.assertEqual(len(surface["objects"]), 202)

    def test_documentation_only_release_keeps_component_selection(self) -> None:
        verified = []
        self.validator.validate_release_tag(
            "docs-release-20260715.1",
            self.manifest,
            publication_validator=lambda manifest: verified.append(manifest),
        )
        self.assertEqual(verified, [self.manifest])

    def test_docs_release_rejects_missing_studio_publication_evidence(self) -> None:
        def load(url: str):
            if "pypi.org" in url:
                return {
                    "info": {"version": self.manifest["python"]["version"]},
                    "urls": [{"filename": "junjo.whl"}],
                }
            return {"draft": False, "published_at": "2026-07-15T00:00:00Z", "assets": []}

        with self.assertRaisesRegex(ValueError, "RELEASE_EVIDENCE.json"):
            self.validator.validate_published_selection(self.manifest, load)

    def test_docs_release_accepts_published_github_pypi_and_studio_evidence(self) -> None:
        def load(url: str):
            if "pypi.org" in url:
                return {
                    "info": {"version": self.manifest["python"]["version"]},
                    "urls": [{"filename": "junjo.whl"}],
                }
            assets = [{"name": "RELEASE_EVIDENCE.json"}] if "studio-v" in url else []
            return {"draft": False, "published_at": "2026-07-15T00:00:00Z", "assets": assets}

        self.validator.validate_published_selection(self.manifest, load)

    def test_docs_release_rejects_tag_only_component_selection(self) -> None:
        def load(url: str):
            if "sdk-python" in url:
                return {"draft": False, "published_at": None, "assets": []}
            return {"draft": False, "published_at": "2026-07-15T00:00:00Z", "assets": []}

        with self.assertRaisesRegex(ValueError, "is not published"):
            self.validator.validate_published_selection(self.manifest, load)

    def test_docs_release_rejects_failed_python_publication(self) -> None:
        def load(url: str):
            if "pypi.org" in url:
                return {
                    "info": {"version": self.manifest["python"]["version"]},
                    "urls": [],
                }
            assets = [{"name": "RELEASE_EVIDENCE.json"}] if "studio-v" in url else []
            return {"draft": False, "published_at": "2026-07-15T00:00:00Z", "assets": assets}

        with self.assertRaisesRegex(ValueError, "not installable from PyPI"):
            self.validator.validate_published_selection(self.manifest, load)

    def test_new_component_release_must_update_its_manifest_entry(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "update tooling/docs/stable-releases.json"
        ):
            self.validator.validate_release_tag("sdk-python-v0.66.0", self.manifest)

    def test_production_promotion_accepts_only_owned_release_namespaces(self) -> None:
        accepted = (
            "sdk-python-v0.65.0",
            "studio-v0.82.0",
            "docs-release-20260715.1",
        )
        for tag in accepted:
            self.assertIsNotNone(self.promoter.RELEASE_TAG.fullmatch(tag), tag)
        for tag in ("v1.0.0", "master", "docs-production", "docs-release-latest"):
            self.assertIsNone(self.promoter.RELEASE_TAG.fullmatch(tag), tag)


if __name__ == "__main__":
    unittest.main()
