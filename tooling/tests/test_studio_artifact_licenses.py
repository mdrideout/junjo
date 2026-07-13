"""Focused tests for Studio production artifact license evidence."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def load_validator() -> ModuleType:
    """Load the dependency-free validator without making tooling a package."""
    path = REPOSITORY_ROOT / "tooling/scripts/validate_studio_artifact_licenses.py"
    specification = importlib.util.spec_from_file_location(
        "studio_artifact_license_validator", path
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


validator = load_validator()


class ArtifactLicenseRepositoryTests(unittest.TestCase):
    """Prove the current repository evidence is complete and lock-bound."""

    def test_current_fast_contract_is_valid(self) -> None:
        policy = validator.load_policy()
        validator.check_inventories(policy, with_cargo_metadata=False)
        validator.validate_image_and_notice_contracts(policy)

    def test_frontend_override_and_production_selection_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            package = root / "package.json"
            lock = root / "package-lock.json"
            package.write_text(
                json.dumps({"dependencies": {"foo": "1.0.0"}}), encoding="utf-8"
            )
            lock.write_text(
                json.dumps(
                    {
                        "lockfileVersion": 3,
                        "packages": {
                            "": {"dependencies": {"foo": "1.0.0"}},
                            "node_modules/foo": {"version": "1.0.0"},
                            "node_modules/test-only": {
                                "dev": True,
                                "license": "GPL-3.0-only",
                                "version": "9.0.0",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            policy = {
                "frontend": {
                    "allowed_license_expressions": ["MIT"],
                    "manual_license_overrides": [
                        {
                            "license": "MIT",
                            "name": "foo",
                            "version": "1.0.0",
                        }
                    ],
                }
            }

            inventory = validator.build_frontend_inventory(
                policy, lock_path=lock, package_path=package
            )

            self.assertEqual(
                inventory["dependencies"],
                [
                    {
                        "license": "MIT",
                        "license_source": "artifact-license-policy override",
                        "name": "foo",
                        "version": "1.0.0",
                    }
                ],
            )
            self.assertEqual(
                inventory["source_lock"]["sha256"], validator.sha256_file(lock)
            )

    def test_frontend_inventory_rejects_unreviewed_license_expression(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            package = root / "package.json"
            lock = root / "package-lock.json"
            package.write_text(
                json.dumps({"dependencies": {"foo": "1.0.0"}}), encoding="utf-8"
            )
            lock.write_text(
                json.dumps(
                    {
                        "lockfileVersion": 3,
                        "packages": {
                            "": {"dependencies": {"foo": "1.0.0"}},
                            "node_modules/foo": {
                                "license": "GPL-3.0-only",
                                "version": "1.0.0",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            policy = {
                "frontend": {
                    "allowed_license_expressions": ["MIT"],
                    "manual_license_overrides": [],
                }
            }

            with self.assertRaisesRegex(RuntimeError, "unreviewed license expression"):
                validator.build_frontend_inventory(
                    policy, lock_path=lock, package_path=package
                )

    def test_frontend_artifact_rejects_source_maps_and_references(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            dist = Path(temporary_directory)
            bundle = dist / "bundle.js"
            bundle.write_text("console.log('ok')\n", encoding="utf-8")
            validator.validate_frontend_build(dist)

            source_map = dist / "bundle.js.map"
            source_map.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "contains source maps"):
                validator.validate_frontend_build(dist)
            source_map.unlink()

            bundle.write_text("//# sourceMappingURL=bundle.js.map\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "references source maps"):
                validator.validate_frontend_build(dist)

    def test_ingestion_inventory_uses_only_normal_linux_closure(self) -> None:
        root_id = "path+file:///fixture#ingestion@1.0.0"
        normal_id = "registry+https://example.invalid/index#normal@1.0.0"
        build_id = "registry+https://example.invalid/index#builder@1.0.0"
        metadata = {
            "packages": [
                {
                    "id": root_id,
                    "license": "Apache-2.0",
                    "name": "ingestion",
                    "source": None,
                    "version": "1.0.0",
                },
                {
                    "id": normal_id,
                    "license": "MIT",
                    "name": "normal",
                    "source": "registry+https://example.invalid/index",
                    "version": "1.0.0",
                },
                {
                    "id": build_id,
                    "license": "MIT",
                    "name": "builder",
                    "source": "registry+https://example.invalid/index",
                    "version": "1.0.0",
                },
            ],
            "resolve": {
                "root": root_id,
                "nodes": [
                    {
                        "deps": [
                            {"dep_kinds": [{"kind": None}], "pkg": normal_id},
                            {"dep_kinds": [{"kind": "build"}], "pkg": build_id},
                        ],
                        "id": root_id,
                    },
                    {"deps": [], "id": normal_id},
                    {"deps": [], "id": build_id},
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            lock = Path(temporary_directory) / "Cargo.lock"
            lock.write_text(
                """version = 4

[[package]]
name = "ingestion"
version = "1.0.0"

[[package]]
name = "normal"
version = "1.0.0"
source = "registry+https://example.invalid/index"
checksum = "normal-checksum"

[[package]]
name = "builder"
version = "1.0.0"
source = "registry+https://example.invalid/index"
checksum = "builder-checksum"
""",
                encoding="utf-8",
            )
            policy = {"ingestion": {"allowed_license_expressions": ["MIT"]}}
            inventory = validator.build_ingestion_inventory(
                policy,
                metadata_by_platform={
                    "linux/amd64": metadata,
                    "linux/arm64": metadata,
                },
                lock_path=lock,
            )

            self.assertEqual(
                inventory["dependencies"],
                [
                    {
                        "checksum": "normal-checksum",
                        "license": "MIT",
                        "name": "normal",
                        "platforms": ["linux/amd64", "linux/arm64"],
                        "source": "registry+https://example.invalid/index",
                        "version": "1.0.0",
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
