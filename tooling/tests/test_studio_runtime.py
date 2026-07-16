"""Focused contract tests for the source-owned Studio Compose runtime."""

from __future__ import annotations

import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROJECT_NAME = "junjo-root-test"


def load_validator() -> ModuleType:
    """Load the dependency-free validator without making tooling a package."""
    path = REPOSITORY_ROOT / "tooling/scripts/validate_studio_runtime.py"
    specification = importlib.util.spec_from_file_location(
        "studio_runtime_validator", path
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


validator = load_validator()


def port(target: int, published: str) -> dict[str, Any]:
    return {
        "mode": "ingress",
        "protocol": "tcp",
        "published": published,
        "target": target,
    }


def mount(
    mount_type: str, source: str, target: str, *, read_only: bool = False
) -> dict[str, Any]:
    return {
        "type": mount_type,
        "source": source,
        "target": target,
        "read_only": read_only,
    }


def source_service(
    project_root: Path, service_name: str, build_target: str
) -> dict[str, Any]:
    return {
        "build": {
            "context": str(project_root),
            "dockerfile": f"{service_name}/Dockerfile",
            "target": build_target,
        },
        "networks": {"junjo-network": None},
        "restart": "unless-stopped",
    }


def base_runtime(project_root: Path, build_target: str) -> dict[str, Any]:
    backend = source_service(project_root, "backend", build_target)
    backend.update(
        {
            "environment": {
                "GRPC_PORT": "50053",
                "INGESTION_HOST": "ingestion",
                "INGESTION_PORT": "50052",
                "JUNJO_METADATA_DB_PATH": "/app/.dbdata/sqlite/metadata.db",
                "JUNJO_PARQUET_STORAGE_PATH": "/app/.dbdata/spans/parquet",
                "JUNJO_SQLITE_PATH": "/app/.dbdata/sqlite/junjo.db",
                "RUN_MIGRATIONS": "true",
            },
            "ports": [port(26154, "26154")],
            "volumes": [
                mount("bind", str(project_root / ".dbdata"), "/app/.dbdata"),
                mount("bind", str(project_root / "backend/app"), "/app/app"),
            ],
        }
    )

    ingestion = source_service(project_root, "ingestion", build_target)
    ingestion.update(
        {
            "depends_on": {
                "backend": {"condition": "service_started", "required": True}
            },
            "environment": {
                "BACKEND_GRPC_HOST": "backend",
                "BACKEND_GRPC_PORT": "50053",
                "GRPC_PORT": "26155",
                "INTERNAL_GRPC_PORT": "50052",
                "JUNJO_API_KEY_CACHE_MAX_ENTRIES": "1024",
                "JUNJO_API_KEY_CACHE_TTL_SECONDS": "10",
                "JUNJO_API_KEY_VALIDATION_MAX_CONCURRENCY": "8",
                "JUNJO_API_KEY_VALIDATION_MAX_PENDING": "32",
                "JUNJO_API_KEY_VALIDATION_TIMEOUT_MS": "2000",
                "PARQUET_OUTPUT_DIR": "/app/.dbdata/spans/parquet",
                "SNAPSHOT_PATH": "/app/.dbdata/spans/hot_snapshot.parquet",
                "WAL_DIR": "/app/.dbdata/spans/wal",
            },
            "healthcheck": copy.deepcopy(validator.INGESTION_HEALTHCHECK),
            "ports": [port(26155, "26155")],
            "volumes": [
                mount("bind", str(project_root / ".dbdata"), "/app/.dbdata"),
                mount(
                    "bind",
                    str(project_root / "ingestion/Cargo.lock"),
                    "/app/Cargo.lock",
                ),
                mount(
                    "bind",
                    str(project_root / "ingestion/Cargo.toml"),
                    "/app/Cargo.toml",
                    read_only=True,
                ),
                mount(
                    "bind",
                    str(project_root / "ingestion/build.rs"),
                    "/app/build.rs",
                    read_only=True,
                ),
                mount(
                    "bind",
                    str(project_root / "ingestion/src"),
                    "/app/src",
                    read_only=True,
                ),
                mount("volume", "ingestion-target-cache", "/app/target"),
                mount(
                    "bind", str(project_root / "proto"), "/proto", read_only=True
                ),
                mount(
                    "volume",
                    "ingestion-cargo-cache",
                    "/usr/local/cargo/registry",
                ),
            ],
        }
    )

    frontend = source_service(project_root, "frontend", build_target)
    frontend.update(
        {
            "depends_on": {
                "backend": {"condition": "service_started", "required": True}
            },
            "ports": [port(26151, "26151"), port(26153, "26153")],
            "volumes": [
                mount("bind", str(project_root / "frontend"), "/app"),
                mount("volume", "frontend-modules", "/app/node_modules"),
            ],
        }
    )

    volume_names = (
        "frontend-modules",
        "ingestion-cargo-cache",
        "ingestion-target-cache",
    )
    return {
        "services": {
            "backend": backend,
            "frontend": frontend,
            "ingestion": ingestion,
        },
        "volumes": {
            name: {"name": f"{PROJECT_NAME}_{name}"} for name in volume_names
        },
        "networks": {
            "junjo-network": {
                "driver": "bridge",
                "name": f"{PROJECT_NAME}_junjo-network",
            }
        },
    }


def monitored_runtime(base: dict[str, Any]) -> dict[str, Any]:
    monitored = copy.deepcopy(base)
    monitored["services"]["cadvisor"] = {
        "image": "gcr.io/cadvisor/cadvisor:v0.47.0",
        "networks": {"default": None},
        "ports": [port(8080, "26156")],
        "restart": "unless-stopped",
        "volumes": [
            mount("bind", "/", "/rootfs", read_only=True),
            mount("bind", "/sys", "/sys", read_only=True),
            mount("bind", "/var/lib/docker", "/var/lib/docker", read_only=True),
            mount("bind", "/var/run", "/var/run", read_only=True),
        ],
    }
    monitored["networks"]["default"] = {"name": f"{PROJECT_NAME}_default"}
    return monitored


class StudioRuntimeContractTests(unittest.TestCase):
    """Prove the base runtime and monitoring overlay reject contract drift."""

    def validate_base(
        self, rendered: dict[str, Any], project_root: Path, build_target: str
    ) -> None:
        validator.validate_base_runtime(
            rendered,
            project_root=project_root,
            project_name=PROJECT_NAME,
            build_target=build_target,
        )

    def test_development_and_production_contracts_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            for build_target in ("development", "production"):
                with self.subTest(build_target=build_target):
                    base = base_runtime(project_root, build_target)
                    self.validate_base(base, project_root, build_target)
                    validator.validate_monitoring_overlay(
                        base,
                        monitored_runtime(base),
                        project_root=project_root,
                        project_name=PROJECT_NAME,
                    )

    def test_base_runtime_rejects_unscoped_or_fallback_resources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            cases = {
                "fallback image": lambda runtime: runtime["services"]["backend"].update(
                    {"image": "example.invalid/backend:latest"}
                ),
                "fixed network": lambda runtime: runtime["networks"][
                    "junjo-network"
                ].update({"name": "junjo_network"}),
                "fixed container": lambda runtime: runtime["services"][
                    "frontend"
                ].update({"container_name": "junjo-frontend"}),
            }
            for label, mutate in cases.items():
                with self.subTest(label=label):
                    runtime = base_runtime(project_root, "development")
                    mutate(runtime)
                    with self.assertRaises(RuntimeError):
                        self.validate_base(runtime, project_root, "development")

    def test_base_runtime_rejects_internal_wiring_or_mount_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            cases = {
                "internal port": lambda runtime: runtime["services"][
                    "ingestion"
                ]["environment"].update({"INTERNAL_GRPC_PORT": "26155"}),
                "healthcheck": lambda runtime: runtime["services"]["ingestion"][
                    "healthcheck"
                ].update({"retries": 1}),
                "writable source": lambda runtime: runtime["services"]["ingestion"][
                    "volumes"
                ][2].update({"read_only": False}),
            }
            for label, mutate in cases.items():
                with self.subTest(label=label):
                    runtime = base_runtime(project_root, "production")
                    mutate(runtime)
                    with self.assertRaises(RuntimeError):
                        self.validate_base(runtime, project_root, "production")

    def test_monitoring_overlay_cannot_change_base_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            base = base_runtime(project_root, "development")
            monitored = monitored_runtime(base)
            monitored["services"]["backend"]["restart"] = "always"
            with self.assertRaisesRegex(RuntimeError, "must not change backend"):
                validator.validate_monitoring_overlay(
                    base,
                    monitored,
                    project_root=project_root,
                    project_name=PROJECT_NAME,
                )

    def test_monitoring_overlay_rejects_unsafe_cadvisor_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            cases = {
                "privileged": lambda runtime: runtime["services"]["cadvisor"].update(
                    {"privileged": True}
                ),
                "writable host": lambda runtime: runtime["services"]["cadvisor"][
                    "volumes"
                ][0].update({"read_only": False}),
                "unexpected service": lambda runtime: runtime["services"].update(
                    {"prometheus": {}}
                ),
            }
            for label, mutate in cases.items():
                with self.subTest(label=label):
                    base = base_runtime(project_root, "development")
                    monitored = monitored_runtime(base)
                    mutate(monitored)
                    with self.assertRaises(RuntimeError):
                        validator.validate_monitoring_overlay(
                            base,
                            monitored,
                            project_root=project_root,
                            project_name=PROJECT_NAME,
                        )

    def test_safe_environment_replaces_active_and_commented_values(self) -> None:
        template_text = """\
JUNJO_BUILD_TARGET=development
JUNJO_ENV=development
# JUNJO_PROD_FRONTEND_URL=
# JUNJO_PROD_BACKEND_URL=
# JUNJO_PROD_INGESTION_URL=
JUNJO_SESSION_SECRET=replace-me
JUNJO_SECURE_COOKIE_KEY=replace-me
JUNJO_SECURE_COOKIE_KEY=also-replace-me
JUNJO_HOST_DB_DATA_PATH=/unsafe/host/path
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / ".env.example"
            destination = root / ".env"
            template.write_text(template_text, encoding="utf-8")
            validator.write_safe_environment(
                template,
                destination,
                runtime_environment="production",
                build_target="production",
            )
            output = destination.read_text(encoding="utf-8")

        self.assertIn("JUNJO_BUILD_TARGET=production\n", output)
        self.assertIn("JUNJO_ENV=production\n", output)
        self.assertIn("JUNJO_HOST_DB_DATA_PATH=./.dbdata\n", output)
        self.assertIn(
            "JUNJO_PROD_INGESTION_URL=https://ingestion.studio.example.test\n",
            output,
        )
        self.assertNotIn("replace-me", output)
        self.assertNotIn("/unsafe/host/path", output)
        for key in (
            "JUNJO_BUILD_TARGET",
            "JUNJO_ENV",
            "JUNJO_HOST_DB_DATA_PATH",
            "JUNJO_PROD_FRONTEND_URL",
            "JUNJO_PROD_BACKEND_URL",
            "JUNJO_PROD_INGESTION_URL",
            "JUNJO_SECURE_COOKIE_KEY",
            "JUNJO_SESSION_SECRET",
        ):
            self.assertEqual(output.count(f"{key}="), 1)


if __name__ == "__main__":
    unittest.main()
