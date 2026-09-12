"""Offline invariants for the completed unified documentation migration."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCS_TOOLING = REPOSITORY_ROOT / "tooling/docs"


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


class DocumentationMigrationTests(unittest.TestCase):
    """Prove retired sources and current public objects stay accounted for."""

    def setUp(self) -> None:
        self.ledger = load_json(DOCS_TOOLING / "content-migration.json")
        self.routes = load_json(DOCS_TOOLING / "legacy-routes.json")
        self.surface = load_json(
            REPOSITORY_ROOT / "sdks/python/docs/api-public-surface.json"
        )

    def test_every_retired_rst_source_is_preserved_in_the_content_ledger(self) -> None:
        self.assertEqual(list((REPOSITORY_ROOT / "sdks/python/docs").glob("*.rst")), [])
        ledger_pages = self.ledger["pages"]
        self.assertEqual(len(ledger_pages), 18)

        for entry in ledger_pages:
            source = REPOSITORY_ROOT / str(entry["source_path"])
            self.assertFalse(source.exists(), source)
            self.assertEqual(entry["status"], "retired-source")
            if entry["disposition"] != "migrated":
                continue
            target = REPOSITORY_ROOT / str(entry["target_path"])
            self.assertTrue(target.is_file(), target)
            # This ledger records the migration snapshot, not a prohibition on
            # later editorial changes. Assembly validates the current bytes.
            self.assertRegex(entry["target_hash"], r"^sha256:[a-f0-9]{64}$")

    def test_repository_source_dispositions_are_final(self) -> None:
        repository_sources = self.ledger["repository_sources"]
        self.assertGreaterEqual(len(repository_sources), 1)
        for entry in repository_sources:
            if entry["disposition"] == "retired-placeholder":
                self.assertFalse((REPOSITORY_ROOT / str(entry["source_path"])).exists())
                self.assertEqual(entry["status"], "retired")
            elif entry["disposition"] == "replaced":
                self.assertFalse((REPOSITORY_ROOT / str(entry["source_path"])).exists())
                self.assertTrue((REPOSITORY_ROOT / str(entry["target_path"])).is_file())
                self.assertEqual(entry["status"], "accounted-for")
            else:
                self.assertTrue((REPOSITORY_ROOT / str(entry["source_path"])).is_file())
                self.assertEqual(entry["status"], "accounted-for")

    def test_every_legacy_page_has_a_live_target_contract(self) -> None:
        pages = self.ledger["pages"]
        route_entries = self.routes["routes"]
        self.assertEqual(
            {entry["source_path"].removeprefix("sdks/python/docs/") for entry in pages},
            {entry["source_document"] for entry in route_entries},
        )
        for entry in route_entries:
            self.assertEqual(entry["status"], "globally-redirected")
            self.assertTrue(entry["source_routes"])
            self.assertEqual(entry["target_route"], "/docs/python/")

    def test_python_api_public_surface_is_complete_and_unique(self) -> None:
        self.assertEqual(self.surface["version"], 2)
        objects = self.surface["objects"]
        modules = self.surface["module_allowlist"]
        identities = {
            (entry["kind"], entry["public_name"], entry["anchor"]) for entry in objects
        }
        self.assertEqual(set(modules), {
            entry["public_name"] for entry in objects if entry["kind"] == "module"
        })
        self.assertGreater(len(objects), len(modules))
        self.assertEqual(len(identities), len(objects))
        self.assertTrue(
            all(not str(entry["kind"]).startswith("py:") for entry in objects)
        )


if __name__ == "__main__":
    unittest.main()
