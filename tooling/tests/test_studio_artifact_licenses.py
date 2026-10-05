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
            inventory = validator.build_rust_inventory(
                policy,
                validator.INGESTION,
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

    def test_backend_inventory_follows_the_workspace_path_dependency(self) -> None:
        root_id = "path+file:///fixture/server#junjo-backend@1.0.0"
        member_id = "path+file:///fixture/evidence#junjo-evidence@1.0.0"
        linked_id = "registry+https://example.invalid/index#linked@1.0.0"
        test_only_id = "registry+https://example.invalid/index#test-only@1.0.0"
        metadata = {
            "packages": [
                {
                    "id": root_id,
                    "license": "Apache-2.0",
                    "name": "junjo-backend",
                    "source": None,
                    "version": "1.0.0",
                },
                {
                    "id": member_id,
                    "license": "Apache-2.0",
                    "name": "junjo-evidence",
                    "source": None,
                    "version": "1.0.0",
                },
                {
                    "id": linked_id,
                    "license": "MIT",
                    "name": "linked",
                    "source": "registry+https://example.invalid/index",
                    "version": "1.0.0",
                },
                {
                    "id": test_only_id,
                    "license": "GPL-3.0-only",
                    "name": "test-only",
                    "source": "registry+https://example.invalid/index",
                    "version": "1.0.0",
                },
            ],
            "resolve": {
                "root": root_id,
                "nodes": [
                    {
                        "deps": [
                            {"dep_kinds": [{"kind": None}], "pkg": member_id},
                            {"dep_kinds": [{"kind": "dev"}], "pkg": test_only_id},
                        ],
                        "id": root_id,
                    },
                    {
                        "deps": [{"dep_kinds": [{"kind": None}], "pkg": linked_id}],
                        "id": member_id,
                    },
                    {"deps": [], "id": linked_id},
                    {"deps": [], "id": test_only_id},
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            lock = Path(temporary_directory) / "Cargo.lock"
            lock.write_text(
                """version = 4

[[package]]
name = "junjo-backend"
version = "1.0.0"

[[package]]
name = "junjo-evidence"
version = "1.0.0"

[[package]]
name = "linked"
version = "1.0.0"
source = "registry+https://example.invalid/index"
checksum = "linked-checksum"

[[package]]
name = "test-only"
version = "1.0.0"
source = "registry+https://example.invalid/index"
checksum = "test-only-checksum"
""",
                encoding="utf-8",
            )
            # Only the registry crate needs a reviewed expression. The two
            # workspace packages are Junjo's own and are not inventory entries.
            policy = {"backend": {"allowed_license_expressions": ["MIT"]}}
            inventory = validator.build_rust_inventory(
                policy,
                validator.BACKEND,
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
                        "checksum": "linked-checksum",
                        "license": "MIT",
                        "name": "linked",
                        "platforms": ["linux/amd64", "linux/arm64"],
                        "source": "registry+https://example.invalid/index",
                        "version": "1.0.0",
                    }
                ],
            )
            self.assertEqual(
                inventory["source_lock"],
                {"path": "backend/Cargo.lock", "sha256": validator.sha256_file(lock)},
            )

    def test_rust_inventory_rejects_unreviewed_license_expression(self) -> None:
        root_id = "path+file:///fixture/server#junjo-backend@1.0.0"
        copyleft_id = "registry+https://example.invalid/index#copyleft@1.0.0"
        metadata = {
            "packages": [
                {
                    "id": root_id,
                    "license": "Apache-2.0",
                    "name": "junjo-backend",
                    "source": None,
                    "version": "1.0.0",
                },
                {
                    "id": copyleft_id,
                    "license": "GPL-3.0-only",
                    "name": "copyleft",
                    "source": "registry+https://example.invalid/index",
                    "version": "1.0.0",
                },
            ],
            "resolve": {
                "root": root_id,
                "nodes": [
                    {
                        "deps": [{"dep_kinds": [{"kind": None}], "pkg": copyleft_id}],
                        "id": root_id,
                    },
                    {"deps": [], "id": copyleft_id},
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            lock = Path(temporary_directory) / "Cargo.lock"
            lock.write_text(
                """version = 4

[[package]]
name = "junjo-backend"
version = "1.0.0"

[[package]]
name = "copyleft"
version = "1.0.0"
source = "registry+https://example.invalid/index"
checksum = "copyleft-checksum"
""",
                encoding="utf-8",
            )
            # An expression reviewed for ingestion is not reviewed for the backend.
            policy = {
                "backend": {"allowed_license_expressions": ["MIT"]},
                "ingestion": {"allowed_license_expressions": ["GPL-3.0-only"]},
            }

            with self.assertRaisesRegex(
                RuntimeError,
                r"unreviewed license expression: copyleft@1\.0\.0 \(GPL-3\.0-only\)",
            ):
                validator.build_rust_inventory(
                    policy,
                    validator.BACKEND,
                    metadata_by_platform={
                        "linux/amd64": metadata,
                        "linux/arm64": metadata,
                    },
                    lock_path=lock,
                )


if __name__ == "__main__":
    unittest.main()
