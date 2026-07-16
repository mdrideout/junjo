#!/usr/bin/env python3
"""Validate the supported Junjo AI Studio deployment distributions.

This command performs offline configuration validation. It renders Compose
configuration with a temporary, non-secret environment file and never builds,
pulls, starts, or contacts a container image registry.
"""

from __future__ import annotations

import argparse
import json
import py_compile
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RELEASE_CONTRACT = DEFAULT_REPOSITORY_ROOT / "tooling/studio_release_contract.json"

BACKEND = "junjo-ai-studio-backend"
INGESTION = "junjo-ai-studio-ingestion"
FRONTEND = "junjo-ai-studio-frontend"
CORE_SERVICES = frozenset({BACKEND, INGESTION, FRONTEND})


@dataclass(frozen=True)
class Distribution:
    """Describe one repository-owned Studio deployment distribution."""

    name: str
    relative_path: Path
    expected_services: frozenset[str]


DISTRIBUTIONS = (
    Distribution(
        name="minimal",
        relative_path=Path("apps/studio/deployments/minimal"),
        expected_services=CORE_SERVICES,
    ),
    Distribution(
        name="vm-caddy",
        relative_path=Path("apps/studio/deployments/vm-caddy"),
        expected_services=CORE_SERVICES | {"junjo-app", "caddy"},
    ),
)

SAFE_ENVIRONMENT = """\
JUNJO_ENV=development
JUNJO_HOST_DB_DATA_PATH=./.dbdata
JUNJO_SESSION_SECRET=validation-only-session-secret
JUNJO_SECURE_COOKIE_KEY=validation-only-cookie-key
JUNJO_INTERNAL_GRPC_TOKEN=validation-internal-grpc-token-32-bytes
CLOUDFLARE_API_TOKEN=validation-only-cloudflare-token
"""

SAFE_ENVIRONMENT_VALUES: dict[str, str] = {
    line.split("=", maxsplit=1)[0]: line.split("=", maxsplit=1)[1]
    for line in SAFE_ENVIRONMENT.splitlines()
    if line
}


def require(condition: bool, message: str) -> None:
    """Raise a clear validation error when an invariant is false."""
    if not condition:
        raise RuntimeError(message)


def load_image_repositories(contract_path: Path) -> dict[str, str]:
    """Load Studio image destinations from the platform release contract."""
    require(contract_path.is_file(), f"Studio release contract is missing: {contract_path}")
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError("Studio release contract contains invalid JSON") from error
    require(isinstance(contract, dict), "Studio release contract must be an object")
    images = contract.get("images")
    require(isinstance(images, dict), "Studio release contract images must be an object")
    require(
        set(images) == {"backend", "frontend", "ingestion"},
        "Studio release contract must define exactly backend, frontend, and ingestion images",
    )
    repositories: dict[str, str] = {}
    for service in ("backend", "frontend", "ingestion"):
        image = images[service]
        require(isinstance(image, dict), f"release image {service} must be an object")
        repository = image.get("repository")
        require(
            isinstance(repository, str) and bool(repository),
            f"release image {service} repository must be a non-empty string",
        )
        repositories[service] = repository
    return repositories


IMAGE_REPOSITORIES = load_image_repositories(DEFAULT_RELEASE_CONTRACT)


def run_command(
    command: list[str],
    *,
    cwd: Path,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a local validation command and include its output on failure."""
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=capture_output,
            text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError(f"required command is unavailable: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        output = "\n".join(
            part.strip() for part in (error.stdout, error.stderr) if part
        )
        message = f"command failed ({' '.join(command)})"
        if output:
            message = f"{message}:\n{output}"
        raise RuntimeError(message) from error


def copy_for_compose_render(source: Path, destination: Path) -> None:
    """Create an isolated Compose project from the shipped environment template."""
    destination.mkdir()
    shutil.copyfile(source / "docker-compose.yml", destination / "docker-compose.yml")
    environment_lines = (
        (source / ".env.example").read_text(encoding="utf-8").splitlines()
    )
    rendered_lines: list[str] = []
    replaced_keys: set[str] = set()
    for line in environment_lines:
        key, separator, _value = line.partition("=")
        stripped_key = key.strip()
        if separator and stripped_key in SAFE_ENVIRONMENT_VALUES:
            rendered_lines.append(
                f"{stripped_key}={SAFE_ENVIRONMENT_VALUES[stripped_key]}"
            )
            replaced_keys.add(stripped_key)
        else:
            rendered_lines.append(line)
    for key, value in SAFE_ENVIRONMENT_VALUES.items():
        if key not in replaced_keys:
            rendered_lines.append(f"{key}={value}")
    (destination / ".env").write_text(
        "\n".join(rendered_lines) + "\n", encoding="utf-8"
    )


def render_compose(distribution_root: Path) -> tuple[dict[str, Any], Path]:
    """Render a deployment with Docker Compose without building or pulling images."""
    with tempfile.TemporaryDirectory(
        prefix="junjo-compose-validation-"
    ) as temp_directory:
        temporary_root = Path(temp_directory) / distribution_root.name
        copy_for_compose_render(distribution_root, temporary_root)
        result = run_command(
            [
                "docker",
                "compose",
                "--project-name",
                f"junjo-{distribution_root.name}-validation",
                "--project-directory",
                str(temporary_root),
                "--env-file",
                str(temporary_root / ".env"),
                "-f",
                str(temporary_root / "docker-compose.yml"),
                "config",
                "--format",
                "json",
            ],
            cwd=temporary_root,
        )
        try:
            rendered = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("Docker Compose returned invalid JSON") from error
    require(
        isinstance(rendered, dict), "rendered Compose configuration must be an object"
    )
    return rendered, temporary_root


def require_environment(
    service: dict[str, Any],
    service_name: str,
    expected: dict[str, str],
) -> None:
    """Validate exact internal environment wiring for one service."""
    environment = service.get("environment", {})
    require(
        isinstance(environment, dict),
        f"{service_name} environment must render as an object",
    )
    for key, value in expected.items():
        require(
            str(environment.get(key)) == value,
            f"{service_name} must set {key}={value}",
        )


def rendered_ports(
    service: dict[str, Any], service_name: str
) -> set[tuple[int, str, str]]:
    """Return normalized published ports for exact contract comparison."""
    ports = service.get("ports", [])
    require(isinstance(ports, list), f"{service_name} ports must render as a list")
    normalized: set[tuple[int, str, str]] = set()
    for item in ports:
        require(
            isinstance(item, dict), f"{service_name} contains an invalid port entry"
        )
        try:
            target = int(item.get("target", -1))
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                f"{service_name} contains an invalid target port"
            ) from error
        normalized.add(
            (target, str(item.get("published")), str(item.get("protocol", "tcp")))
        )
    return normalized


def require_exact_ports(
    service: dict[str, Any],
    service_name: str,
    expected: set[tuple[int, str, str]],
) -> None:
    """Validate the complete published-port surface for one service."""
    actual = rendered_ports(service, service_name)
    require(
        actual == expected,
        f"{service_name} ports must be exactly {expected}; found {actual}",
    )


def require_dependency(
    service: dict[str, Any], service_name: str, dependency: str
) -> None:
    """Validate that a rendered service depends on another required service."""
    depends_on = service.get("depends_on", {})
    require(
        isinstance(depends_on, dict),
        f"{service_name} dependencies must render as an object",
    )
    dependency_config = depends_on.get(dependency)
    require(
        isinstance(dependency_config, dict),
        f"{service_name} must depend on {dependency}",
    )
    require(
        dependency_config.get("condition") == "service_started",
        f"{service_name} must wait for {dependency} to start",
    )


def require_network(service: dict[str, Any], service_name: str) -> None:
    """Validate that a service participates in the shared Junjo network."""
    networks = service.get("networks", {})
    require(
        isinstance(networks, dict) and set(networks) == {"junjo-network"},
        f"{service_name} must use only junjo-network",
    )


def require_shared_data_mount(
    backend: dict[str, Any], ingestion: dict[str, Any]
) -> None:
    """Validate the backend and ingestion shared persistent data mount."""

    def data_source(service: dict[str, Any], service_name: str) -> str:
        volumes = service.get("volumes", [])
        for volume in volumes:
            if isinstance(volume, dict) and volume.get("target") == "/app/.dbdata":
                source = volume.get("source")
                require(
                    isinstance(source, str),
                    f"{service_name} data mount must have a source",
                )
                return source
        raise RuntimeError(f"{service_name} must mount /app/.dbdata")

    require(
        data_source(backend, BACKEND) == data_source(ingestion, INGESTION),
        "backend and ingestion must share the same /app/.dbdata source",
    )


def validate_rendered_compose(
    distribution: Distribution,
    rendered: dict[str, Any],
    studio_version: str,
    project_root: Path,
) -> None:
    """Validate service topology, image pins, ports, and internal wiring."""
    services = rendered.get("services", {})
    require(
        isinstance(services, dict),
        f"{distribution.name}: services must render as an object",
    )
    require(
        set(services) == set(distribution.expected_services),
        f"{distribution.name}: expected services {sorted(distribution.expected_services)}, "
        f"found {sorted(services)}",
    )

    expected_images = {
        BACKEND: f"{IMAGE_REPOSITORIES['backend']}:{studio_version}",
        INGESTION: f"{IMAGE_REPOSITORIES['ingestion']}:{studio_version}",
        FRONTEND: f"{IMAGE_REPOSITORIES['frontend']}:{studio_version}",
    }
    studio_images: dict[str, str] = {}
    for service_name, service in services.items():
        require(
            isinstance(service, dict),
            f"{distribution.name}: {service_name} must be an object",
        )
        require(
            "container_name" not in service,
            f"{distribution.name}: {service_name} must use a Compose project-scoped container name",
        )
        image = service.get("image")
        if isinstance(image, str) and any(
            image.startswith(f"{repository}:")
            for repository in IMAGE_REPOSITORIES.values()
        ):
            studio_images[service_name] = image
    require(
        studio_images == expected_images,
        f"{distribution.name}: Studio image pins must exactly match {expected_images}; "
        f"found {studio_images}",
    )

    backend = services[BACKEND]
    ingestion = services[INGESTION]
    frontend = services[FRONTEND]

    require_exact_ports(backend, BACKEND, {(26154, "26154", "tcp")})
    require_exact_ports(ingestion, INGESTION, {(26155, "26155", "tcp")})
    require_exact_ports(frontend, FRONTEND, {(26153, "26153", "tcp")})
    for service_name in CORE_SERVICES:
        require(
            "build" not in services[service_name],
            f"{service_name} must use only its pinned image",
        )
    require_environment(
        backend,
        BACKEND,
        {
            "INGESTION_HOST": INGESTION,
            "INGESTION_PORT": "50052",
            "GRPC_PORT": "50053",
            "RUN_MIGRATIONS": "true",
            "JUNJO_SQLITE_PATH": "/app/.dbdata/sqlite/junjo.db",
            "JUNJO_METADATA_DB_PATH": "/app/.dbdata/sqlite/metadata.db",
            "JUNJO_PARQUET_STORAGE_PATH": "/app/.dbdata/spans/parquet",
        },
    )
    require_environment(
        ingestion,
        INGESTION,
        {
            "BACKEND_GRPC_HOST": BACKEND,
            "BACKEND_GRPC_PORT": "50053",
            "GRPC_PORT": "26155",
            "INTERNAL_GRPC_PORT": "50052",
            "JUNJO_API_KEY_CACHE_MAX_ENTRIES": "1024",
            "JUNJO_API_KEY_CACHE_TTL_SECONDS": "10",
            "JUNJO_API_KEY_VALIDATION_MAX_CONCURRENCY": "8",
            "JUNJO_API_KEY_VALIDATION_MAX_PENDING": "32",
            "JUNJO_API_KEY_VALIDATION_TIMEOUT_MS": "2000",
            "WAL_DIR": "/app/.dbdata/spans/wal",
            "SNAPSHOT_PATH": "/app/.dbdata/spans/hot_snapshot.parquet",
            "PARQUET_OUTPUT_DIR": "/app/.dbdata/spans/parquet",
        },
    )
    require_dependency(ingestion, INGESTION, BACKEND)
    require_dependency(frontend, FRONTEND, BACKEND)
    for service_name in CORE_SERVICES:
        require_network(services[service_name], service_name)
    networks = rendered.get("networks", {})
    require(
        isinstance(networks, dict) and set(networks) == {"junjo-network"},
        f"{distribution.name}: junjo-network must be the only declared network",
    )
    network = networks["junjo-network"]
    expected_network_name = f"junjo-{project_root.name}-validation_junjo-network"
    require(
        isinstance(network, dict)
        and network.get("name") == expected_network_name
        and network.get("driver") == "bridge",
        f"{distribution.name}: junjo-network must render as the project-scoped "
        f"{expected_network_name} bridge",
    )
    require_shared_data_mount(backend, ingestion)

    healthcheck = ingestion.get("healthcheck", {})
    expected_healthcheck = {
        "test": ["CMD", "/bin/grpc_health_probe", "-addr=localhost:50052"],
        "timeout": "3s",
        "interval": "5s",
        "retries": 5,
        "start_period": "30s",
    }
    require(
        healthcheck == expected_healthcheck,
        f"{INGESTION} healthcheck must be exactly {expected_healthcheck}; found {healthcheck}",
    )

    if distribution.name == "minimal":
        require(
            not rendered.get("volumes"),
            "minimal: must not add named infrastructure volumes",
        )
    elif distribution.name == "vm-caddy":
        expected_build_contexts = {
            "junjo-app": str((project_root / "junjo_app").resolve()),
            "caddy": str((project_root / "caddy").resolve()),
        }
        for service_name, expected_context in expected_build_contexts.items():
            build = services[service_name].get("build")
            require(
                isinstance(build, dict),
                f"vm-caddy: {service_name} must be built locally",
            )
            require(
                Path(str(build.get("context"))).resolve() == Path(expected_context)
                and build.get("dockerfile") == "Dockerfile",
                f"vm-caddy: {service_name} must use local context {expected_context} and Dockerfile",
            )
            require(
                "image" not in services[service_name],
                f"vm-caddy: {service_name} must not use a remote image",
            )
        require_dependency(services["junjo-app"], "junjo-app", INGESTION)
        require_dependency(services["caddy"], "caddy", BACKEND)
        require_dependency(services["caddy"], "caddy", FRONTEND)
        require_network(services["junjo-app"], "junjo-app")
        require_network(services["caddy"], "caddy")
        require_exact_ports(services["junjo-app"], "junjo-app", set())
        require_exact_ports(
            services["caddy"],
            "caddy",
            {(80, "80", "tcp"), (443, "443", "tcp"), (443, "443", "udp")},
        )
        volumes = rendered.get("volumes", {})
        require(
            isinstance(volumes, dict) and set(volumes) == {"caddy_data"},
            "vm-caddy: caddy_data must be the only named volume",
        )


def validate_setup_cli(distribution_root: Path, distribution_name: str) -> None:
    """Compile a setup CLI in temporary storage and exercise its help surfaces."""
    script = distribution_root / "scripts" / "junjo"
    require(script.is_file(), f"{distribution_name}: setup CLI is missing: {script}")
    require(
        script.stat().st_mode & 0o111 != 0,
        f"{distribution_name}: setup CLI must be executable",
    )
    with tempfile.TemporaryDirectory(prefix="junjo-setup-compile-") as temp_directory:
        compiled = Path(temp_directory) / f"{distribution_name}.pyc"
        try:
            py_compile.compile(str(script), cfile=str(compiled), doraise=True)
        except py_compile.PyCompileError as error:
            raise RuntimeError(
                f"{distribution_name}: setup CLI does not compile: {error.msg}"
            ) from error

    for arguments in (["--help"], ["setup", "--help"]):
        result = run_command(
            [sys.executable, str(script), *arguments], cwd=script.parent.parent
        )
        require(
            "usage:" in result.stdout.lower(),
            f"{distribution_name}: setup help did not render",
        )


def validate_distribution_content(
    distribution_root: Path,
    distribution: Distribution,
    studio_version: str,
) -> None:
    """Validate one distribution without relying on monorepo location or Git state."""
    require(
        distribution_root.is_dir(), f"missing deployment directory: {distribution_root}"
    )
    require(
        (distribution_root / "docker-compose.yml").is_file(),
        f"{distribution.name}: docker-compose.yml is missing",
    )
    require(
        (distribution_root / ".env.example").is_file(),
        f"{distribution.name}: .env.example is missing",
    )
    rendered, project_root = render_compose(distribution_root)
    validate_rendered_compose(
        distribution,
        rendered,
        studio_version,
        project_root,
    )
    validate_setup_cli(distribution_root, distribution.name)


def validate_env_backup_ignore(
    repository_root: Path, distribution: Distribution
) -> None:
    """Prove with Git that a secret-bearing setup backup cannot be tracked accidentally."""
    backup = distribution.relative_path / ".env.bak"
    try:
        result = run_command(
            ["git", "check-ignore", "--verbose", "--", str(backup)],
            cwd=repository_root,
        )
    except RuntimeError as error:
        raise RuntimeError(f"{distribution.name}: Git must ignore {backup}") from error
    expected_ignore_file = str(distribution.relative_path / ".gitignore")
    require(
        expected_ignore_file in result.stdout,
        f"{distribution.name}: {backup} must be ignored explicitly by {expected_ignore_file}",
    )


def validate_distribution(
    repository_root: Path,
    distribution: Distribution,
    studio_version: str,
) -> None:
    """Validate one deployment distribution."""
    distribution_root = repository_root / distribution.relative_path
    validate_distribution_content(distribution_root, distribution, studio_version)
    validate_env_backup_ignore(repository_root, distribution)
    print(f"Validated Studio deployment: {distribution.name}")


def build_parser() -> argparse.ArgumentParser:
    """Build the deployment validation command-line parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate Studio deployment Compose topology, version pins, setup CLIs, "
            "and secret-backup ignore rules without pulling images."
        )
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=DEFAULT_REPOSITORY_ROOT,
        help="Junjo repository root (default: inferred from this script).",
    )
    parser.add_argument(
        "--distribution",
        choices=[distribution.name for distribution in DISTRIBUTIONS],
        help="Validate one exported distribution instead of canonical source.",
    )
    parser.add_argument(
        "--distribution-root",
        type=Path,
        help="Exported distribution directory to validate.",
    )
    parser.add_argument(
        "--studio-version",
        help="Expected Studio version for an exported distribution.",
    )
    return parser


def main() -> int:
    """Validate every supported Studio deployment distribution."""
    args = build_parser().parse_args()
    external_arguments = (
        args.distribution,
        args.distribution_root,
        args.studio_version,
    )
    if any(value is not None for value in external_arguments):
        require(
            all(value is not None for value in external_arguments),
            "--distribution, --distribution-root, and --studio-version must be provided together",
        )
        distribution = next(
            item for item in DISTRIBUTIONS if item.name == args.distribution
        )
        validate_distribution_content(
            args.distribution_root.resolve(),
            distribution,
            args.studio_version,
        )
        print(f"Validated exported Studio deployment: {distribution.name}")
        return 0

    repository_root = args.repository_root.resolve()
    version_file = repository_root / "apps" / "studio" / "VERSION"
    require(version_file.is_file(), f"Studio version file is missing: {version_file}")
    studio_version = version_file.read_text(encoding="utf-8").strip()
    require(bool(studio_version), "Studio version must not be empty")
    for distribution in DISTRIBUTIONS:
        validate_distribution(repository_root, distribution, studio_version)
    print(f"All Studio deployments are valid for Studio {studio_version}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
