"""Offline invariants for the unified documentation migration."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCS_TOOLING = REPOSITORY_ROOT / "tooling/docs"


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


class DocumentationMigrationTests(unittest.TestCase):
    """Prove every legacy source and API object stays explicitly accounted for."""

    def setUp(self) -> None:
        self.ledger = load_json(DOCS_TOOLING / "content-migration.json")
        self.routes = load_json(DOCS_TOOLING / "legacy-routes.json")
        self.baseline = load_json(REPOSITORY_ROOT / "sdks/python/docs/api-sphinx-baseline.json")

    def assert_ledger_file_current(self, entry: dict[str, object]) -> None:
        source = REPOSITORY_ROOT / str(entry["source_path"])
        self.assertTrue(source.is_file(), source)
        self.assertEqual(entry["source_hash"], file_hash(source), source)
        self.assertEqual(
            entry["source_lines"],
            len(source.read_text(encoding="utf-8").splitlines()),
            source,
        )

    def test_every_sphinx_source_is_in_the_content_ledger(self) -> None:
        actual_sources = {
            str(path.relative_to(REPOSITORY_ROOT)) for path in (REPOSITORY_ROOT / "sdks/python/docs").glob("*.rst")
        }
        ledger_pages = self.ledger["pages"]
        ledger_sources = {entry["source_path"] for entry in ledger_pages}
        self.assertEqual(actual_sources, ledger_sources)
        self.assertEqual(len(ledger_pages), 18)

        for entry in ledger_pages:
            self.assert_ledger_file_current(entry)
            if entry["disposition"] != "migrated":
                continue
            target = REPOSITORY_ROOT / str(entry["target_path"])
            self.assertTrue(target.is_file(), target)
            self.assertEqual(entry["target_hash"], file_hash(target), target)

    def test_retained_repository_sources_are_current(self) -> None:
        repository_sources = self.ledger["repository_sources"]
        self.assertGreaterEqual(len(repository_sources), 1)
        for entry in repository_sources:
            self.assert_ledger_file_current(entry)
            self.assertEqual(entry["status"], "accounted-for")

    def test_every_legacy_page_has_a_live_target_contract(self) -> None:
        pages = self.ledger["pages"]
        route_entries = self.routes["routes"]
        self.assertEqual(
            {entry["source_path"].removeprefix("sdks/python/docs/") for entry in pages},
            {entry["source_document"] for entry in route_entries},
        )
        for entry in route_entries:
            self.assertEqual(entry["status"], "mapped")
            self.assertTrue(entry["source_routes"])
            self.assertTrue(str(entry["target_route"]).startswith("/docs/"))

    def test_sphinx_api_baseline_is_complete_and_unique(self) -> None:
        objects = self.baseline["objects"]
        modules = self.baseline["module_allowlist"]
        identities = {(entry["kind"], entry["name"], entry["legacy_uri"]) for entry in objects}
        self.assertEqual(len(modules), 12)
        self.assertEqual(len(objects), 424)
        self.assertEqual(len(identities), len(objects))
        self.assertTrue(all(str(entry["kind"]).startswith("py:") for entry in objects))


if __name__ == "__main__":
    unittest.main()
