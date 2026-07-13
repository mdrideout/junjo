#!/usr/bin/env python3
"""Validate the source-owned Studio Compose runtime without starting containers."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BASE_SERVICES = frozenset({"backend", "frontend", "ingestion"})
ENV_ASSIGNMENT = re.compile(r"^\s*(?:#\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*=.*$")
INGESTION_HEALTHCHECK = {
    "test": ["CMD", "/bin/grpc_health_probe", "-addr=localhost:50052"],
    "timeout": "3s",
    "interval": "5s",
    "retries": 5,
    "start_period": "30s",
}


def require(condition: bool, message: str) -> None:
    """Raise a clear validation failure when a runtime contract is violated."""
    if not condition:
        raise RuntimeError(message)


def run_command(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one offline command and include its output when it fails."""
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError(f"required command is unavailable: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        output = "\n".join(
            part.strip() for part in (error.stdout, error.stderr) if part
        )
        message = f"command failed: {' '.join(command)}"
        if output:
            message = f"{message}:\n{output}"
        raise RuntimeError(message) from error


def write_safe_environment(
    template: Path,
    destination: Path,
    *,
    runtime_environment: str,
    build_target: str,
) -> None:
    """Materialize a non-secret environment from the committed template."""
    updates = {
        "JUNJO_BUILD_TARGET": build_target,
        "JUNJO_ENV": runtime_environment,
        "JUNJO_HOST_DB_DATA_PATH": "./.dbdata",
        "JUNJO_PROD_BACKEND_URL": "https://api.studio.example.test",
        "JUNJO_PROD_FRONTEND_URL": "https://studio.example.test",
        "JUNJO_PROD_INGESTION_URL": "https://ingestion.studio.example.test",
        "JUNJO_SECURE_COOKIE_KEY": (
            "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE="
        ),
        "JUNJO_SESSION_SECRET": "YmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmI=",
    }
    lines = template.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    written: set[str] = set()
    for line in lines:
        match = ENV_ASSIGNMENT.match(line)
        key = match.group(1) if match else None
        if key in updates:
            if key not in written:
                output.append(f"{key}={updates[key]}")
                written.add(key)
            continue
        output.append(line)
    for key, value in updates.items():
        if key not in written:
            output.append(f"{key}={value}")
    destination.write_text("\n".join(output) + "\n", encoding="utf-8")


def render_compose(
    project_root: Path,
    project_name: str,
    compose_files: list[str],
) -> dict[str, Any]:
    """Render one root Studio Compose combination without building or pulling."""
    command = [
        "docker",
        "compose",
        "--project-name",
        project_name,
        "--project-directory",
        str(project_root),
        "--env-file",
        str(project_root / ".env"),
    ]
    for compose_file in compose_files:
        command.extend(["-f", str(project_root / compose_file)])
    command.extend(["config", "--format", "json"])
    result = run_command(command, cwd=project_root)
    try:
        rendered = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Docker Compose returned invalid JSON") from error
    require(isinstance(rendered, dict), "rendered Compose config must be an object")
    return rendered


def require_exact_ports(
    service: dict[str, Any], service_name: str, expected: set[tuple[int, str, str]]
) -> None:
    """Validate the complete host-port surface for one runtime service."""
    ports = service.get("ports", [])
    require(isinstance(ports, list), f"{service_name} ports must be a list")
    actual: set[tuple[int, str, str]] = set()
    for port in ports:
        require(isinstance(port, dict), f"{service_name} port entry must be an object")
        actual.add(
            (
                int(port.get("target", -1)),
                str(port.get("published")),
                str(port.get("protocol", "tcp")),
            )
        )
    require(
        actual == expected,
        f"{service_name} ports must be exactly {expected}; found {actual}",
    )


def require_build(
    service: dict[str, Any],
    service_name: str,
    project_root: Path,
    build_target: str,
) -> None:
    """Validate one source-built service's context, Dockerfile, and target."""
    build = service.get("build")
    require(isinstance(build, dict), f"{service_name} must define a build")
    require(
        Path(str(build.get("context"))).resolve() == project_root.resolve(),
        f"{service_name} build context must be the Studio root",
    )
    require(
        build.get("dockerfile") == f"{service_name}/Dockerfile",
        f"{service_name} must use {service_name}/Dockerfile",
    )
    require(
        build.get("target") == build_target,
        f"{service_name} build target must be {build_target}",
    )
    require("image" not in service, f"{service_name} must not use a fallback image")


def require_dependency(
    service: dict[str, Any], service_name: str, dependency: str
) -> None:
    """Validate one required service-start dependency."""
    dependencies = service.get("depends_on")
    require(isinstance(dependencies, dict), f"{service_name} dependencies must be an object")
    dependency_config = dependencies.get(dependency)
    require(
        isinstance(dependency_config, dict)
        and dependency_config.get("condition") == "service_started",
        f"{service_name} must wait for {dependency} to start",
    )


def require_environment(
    service: dict[str, Any], service_name: str, expected: dict[str, str]
) -> None:
    """Validate exact internal service wiring despite the shared env file."""
    environment = service.get("environment")
    require(isinstance(environment, dict), f"{service_name} environment must be an object")
    for key, value in expected.items():
        require(
            str(environment.get(key)) == value,
            f"{service_name} must set {key}={value}",
        )


def require_mounts(
    service: dict[str, Any],
    service_name: str,
    project_root: Path,
    expected: dict[str, tuple[str, str, bool]],
) -> None:
    """Validate every bind and named-volume mount for one service."""
    volumes = service.get("volumes", [])
    require(isinstance(volumes, list), f"{service_name} volumes must be a list")
    by_target: dict[str, dict[str, Any]] = {}
    for volume in volumes:
        require(isinstance(volume, dict), f"{service_name} volume must be an object")
        target = volume.get("target")
        require(isinstance(target, str), f"{service_name} volume target must be a string")
        require(target not in by_target, f"{service_name} repeats volume target {target}")
        by_target[target] = volume
    require(
        set(by_target) == set(expected),
        f"{service_name} volume targets must be exactly {sorted(expected)}; "
        f"found {sorted(by_target)}",
    )
    for target, (mount_type, source, read_only) in expected.items():
        volume = by_target[target]
        require(
            volume.get("type") == mount_type,
            f"{service_name} {target} must be a {mount_type} mount",
        )
        actual_source = volume.get("source")
        if mount_type == "bind" and source != "/":
            expected_source = (
                Path(source) if source.startswith("/") else project_root / source
            )
            require(
                Path(str(actual_source)).resolve() == expected_source.resolve(),
                f"{service_name} {target} must mount {expected_source}",
            )
        else:
            require(
                actual_source == source,
                f"{service_name} {target} must use source {source}",
            )
        require(
            bool(volume.get("read_only", False)) is read_only,
            f"{service_name} {target} read-only state must be {read_only}",
        )


def validate_base_runtime(
    rendered: dict[str, Any],
    *,
    project_root: Path,
    project_name: str,
    build_target: str,
) -> None:
    """Validate the root source runtime independently of release distributions."""
    services = rendered.get("services")
    require(isinstance(services, dict), "root runtime services must be an object")
    require(
        set(services) == set(BASE_SERVICES),
        f"root runtime services must be exactly {sorted(BASE_SERVICES)}",
    )
    for service_name in BASE_SERVICES:
        service = services[service_name]
        require(isinstance(service, dict), f"{service_name} must be an object")
        require("container_name" not in service, f"{service_name} must be project-scoped")
        require(not service.get("privileged", False), f"{service_name} must not be privileged")
        require(
            service.get("restart") == "unless-stopped",
            f"{service_name} restart policy must be unless-stopped",
        )
        require(
            service.get("networks") == {"junjo-network": None},
            f"{service_name} must use only junjo-network",
        )
        require_build(service, service_name, project_root, build_target)

    backend = services["backend"]
    frontend = services["frontend"]
    ingestion = services["ingestion"]
    require_exact_ports(backend, "backend", {(26154, "26154", "tcp")})
    require_exact_ports(ingestion, "ingestion", {(26155, "26155", "tcp")})
    require_exact_ports(
        frontend,
        "frontend",
        {(26151, "26151", "tcp"), (26153, "26153", "tcp")},
    )
    require_dependency(ingestion, "ingestion", "backend")
    require_dependency(frontend, "frontend", "backend")
    require_environment(
        backend,
        "backend",
        {
            "GRPC_PORT": "50053",
            "INGESTION_HOST": "ingestion",
            "INGESTION_PORT": "50052",
            "JUNJO_METADATA_DB_PATH": "/app/.dbdata/sqlite/metadata.db",
            "JUNJO_PARQUET_STORAGE_PATH": "/app/.dbdata/spans/parquet",
            "JUNJO_SQLITE_PATH": "/app/.dbdata/sqlite/junjo.db",
            "RUN_MIGRATIONS": "true",
        },
    )
    require_environment(
        ingestion,
        "ingestion",
        {
            "BACKEND_GRPC_HOST": "backend",
            "BACKEND_GRPC_PORT": "50053",
            "GRPC_PORT": "26155",
            "INTERNAL_GRPC_PORT": "50052",
            "PARQUET_OUTPUT_DIR": "/app/.dbdata/spans/parquet",
            "SNAPSHOT_PATH": "/app/.dbdata/spans/hot_snapshot.parquet",
            "WAL_DIR": "/app/.dbdata/spans/wal",
        },
    )
    require(
        ingestion.get("healthcheck") == INGESTION_HEALTHCHECK,
        f"ingestion healthcheck must be exactly {INGESTION_HEALTHCHECK}",
    )
    require_mounts(
        backend,
        "backend",
        project_root,
        {
            "/app/.dbdata": ("bind", ".dbdata", False),
            "/app/app": ("bind", "backend/app", False),
        },
    )
    require_mounts(
        ingestion,
        "ingestion",
        project_root,
        {
            "/app/.dbdata": ("bind", ".dbdata", False),
            "/app/Cargo.lock": ("bind", "ingestion/Cargo.lock", False),
            "/app/Cargo.toml": ("bind", "ingestion/Cargo.toml", True),
            "/app/build.rs": ("bind", "ingestion/build.rs", True),
            "/app/src": ("bind", "ingestion/src", True),
            "/app/target": ("volume", "ingestion-target-cache", False),
            "/proto": ("bind", "proto", True),
            "/usr/local/cargo/registry": (
                "volume",
                "ingestion-cargo-cache",
                False,
            ),
        },
    )
    require_mounts(
        frontend,
        "frontend",
        project_root,
        {
            "/app": ("bind", "frontend", False),
            "/app/node_modules": ("volume", "frontend-modules", False),
        },
    )

    volumes = rendered.get("volumes")
    expected_volume_names = {
        "frontend-modules",
        "ingestion-cargo-cache",
        "ingestion-target-cache",
    }
    require(
        isinstance(volumes, dict) and set(volumes) == expected_volume_names,
        f"root runtime named volumes must be exactly {sorted(expected_volume_names)}",
    )
    for name in expected_volume_names:
        require(
            volumes[name].get("name") == f"{project_name}_{name}",
            f"root runtime volume {name} must be project-scoped",
        )

    networks = rendered.get("networks")
    require(
        isinstance(networks, dict) and set(networks) == {"junjo-network"},
        "root runtime must declare only junjo-network",
    )
    network = networks["junjo-network"]
    require(
        isinstance(network, dict)
        and network.get("name") == f"{project_name}_junjo-network"
        and network.get("driver") == "bridge",
        "root runtime junjo-network must be a project-scoped bridge",
    )


def validate_monitoring_overlay(
    base_rendered: dict[str, Any],
    monitored_rendered: dict[str, Any],
    *,
    project_root: Path,
    project_name: str,
) -> None:
    """Validate that monitoring adds only the explicit cAdvisor service."""
    base_services = base_rendered.get("services")
    services = monitored_rendered.get("services")
    require(isinstance(base_services, dict), "base services must be an object")
    require(isinstance(services, dict), "monitored services must be an object")
    require(
        set(services) == set(BASE_SERVICES) | {"cadvisor"},
        "monitoring overlay must add only cadvisor",
    )
    for service_name in BASE_SERVICES:
        require(
            services[service_name] == base_services[service_name],
            f"monitoring overlay must not change {service_name}",
        )
    require(
        monitored_rendered.get("volumes") == base_rendered.get("volumes"),
        "monitoring overlay must not change runtime volumes",
    )

    cadvisor = services["cadvisor"]
    require(isinstance(cadvisor, dict), "cadvisor must be an object")
    allowed_fields = {
        "command",
        "entrypoint",
        "image",
        "networks",
        "ports",
        "restart",
        "volumes",
    }
    require(
        set(cadvisor) <= allowed_fields,
        f"cadvisor contains unsupported fields: {sorted(set(cadvisor) - allowed_fields)}",
    )
    require(
        cadvisor.get("image") == "gcr.io/cadvisor/cadvisor:v0.47.0",
        "cadvisor image must be pinned to v0.47.0",
    )
    require("build" not in cadvisor, "cadvisor must not define a local build")
    require("container_name" not in cadvisor, "cadvisor must be project-scoped")
    require(not cadvisor.get("privileged", False), "cadvisor must not be privileged")
    require(
        cadvisor.get("restart") == "unless-stopped",
        "cadvisor restart policy must be unless-stopped",
    )
    require(
        cadvisor.get("networks") == {"default": None},
        "cadvisor must use only the project-scoped default network",
    )
    require_exact_ports(cadvisor, "cadvisor", {(8080, "26156", "tcp")})
    require_mounts(
        cadvisor,
        "cadvisor",
        project_root,
        {
            "/rootfs": ("bind", "/", True),
            "/sys": ("bind", "/sys", True),
            "/var/lib/docker": ("bind", "/var/lib/docker", True),
            "/var/run": ("bind", "/var/run", True),
        },
    )
    networks = monitored_rendered.get("networks")
    require(
        isinstance(networks, dict)
        and set(networks) == {"default", "junjo-network"},
        "monitored runtime must declare only default and junjo-network",
    )
    require(
        networks.get("junjo-network") == base_rendered.get("networks", {}).get(
            "junjo-network"
        ),
        "monitoring overlay must not change junjo-network",
    )
    default_network = networks["default"]
    require(
        isinstance(default_network, dict)
        and default_network.get("name") == f"{project_name}_default",
        "monitoring default network must be project-scoped",
    )


def validate_runtime_source(repository_root: Path) -> None:
    """Render and validate development and production root runtime contracts."""
    studio_root = repository_root / "apps/studio"
    required_files = (".env.example", "compose.yaml", "compose.monitoring.yaml")
    for filename in required_files:
        require((studio_root / filename).is_file(), f"Studio runtime file is missing: {filename}")

    for runtime_environment, build_target in (
        ("development", "development"),
        ("production", "production"),
    ):
        with tempfile.TemporaryDirectory(
            prefix=f"junjo-root-{runtime_environment}-validation-"
        ) as directory:
            project_root = Path(directory) / "studio"
            project_root.mkdir()
            for filename in ("compose.yaml", "compose.monitoring.yaml"):
                shutil.copyfile(studio_root / filename, project_root / filename)
            write_safe_environment(
                studio_root / ".env.example",
                project_root / ".env",
                runtime_environment=runtime_environment,
                build_target=build_target,
            )
            project_name = f"junjo-root-{runtime_environment}-validation"
            base_rendered = render_compose(
                project_root, project_name, ["compose.yaml"]
            )
            validate_base_runtime(
                base_rendered,
                project_root=project_root,
                project_name=project_name,
                build_target=build_target,
            )
            monitored_rendered = render_compose(
                project_root,
                project_name,
                ["compose.yaml", "compose.monitoring.yaml"],
            )
            validate_monitoring_overlay(
                base_rendered,
                monitored_rendered,
                project_root=project_root,
                project_name=project_name,
            )
        print(
            f"Validated root Studio {runtime_environment} runtime and monitoring overlay."
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Safely render and validate the source-owned Studio base runtime and "
            "monitoring overlay without building, pulling, or starting containers."
        )
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=DEFAULT_REPOSITORY_ROOT,
        help="Junjo repository root (default: inferred from this script).",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    validate_runtime_source(args.repository_root.resolve())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
