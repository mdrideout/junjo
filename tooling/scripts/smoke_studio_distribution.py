#!/usr/bin/env python3
"""Prove that an exact Studio distribution accepts and exposes real telemetry."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VERSION_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
CORE_SERVICES = ("backend", "frontend", "ingestion")
COMPOSE_CORE_SERVICES = (
    "junjo-ai-studio-backend",
    "junjo-ai-studio-frontend",
    "junjo-ai-studio-ingestion",
)
EXACT_IMAGE_OVERRIDE = ".junjo-smoke-exact-images.json"
DEMO_SERVICE_NAME = "Junjo Deployment Example"
DEMO_WORKFLOW_NAME = "Example Deployment Workflow"
SENSITIVE_ENVIRONMENT_KEYS = {
    "CLOUDFLARE_API_TOKEN",
    "JUNJO_AI_STUDIO_API_KEY",
    "JUNJO_SECURE_COOKIE_KEY",
    "JUNJO_SESSION_SECRET",
}


class SmokeError(RuntimeError):
    """A safe, user-facing smoke-test failure."""


@dataclass(frozen=True)
class PublishedImage:
    """Bind one Studio service to its expected registry repository and digest."""

    service: str
    repository: str
    digest: str


def require(condition: bool, message: str) -> None:
    """Raise a smoke failure when an explicit contract is not satisfied."""
    if not condition:
        raise SmokeError(message)


def load_image_repositories(repository_root: Path) -> dict[str, str]:
    """Load the only allowed Studio image destinations from the release contract."""
    contract_path = repository_root / "tooling/studio_release_contract.json"
    require(contract_path.is_file(), f"Studio release contract is missing: {contract_path}")
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SmokeError("Studio release contract contains invalid JSON") from error
    require(isinstance(contract, dict), "Studio release contract must be an object")
    images = contract.get("images")
    require(isinstance(images, dict), "Studio release contract images must be an object")
    require(
        set(images) == set(CORE_SERVICES),
        "Studio release contract must define exactly backend, frontend, and ingestion",
    )
    repositories: dict[str, str] = {}
    for service in CORE_SERVICES:
        image = images[service]
        require(isinstance(image, dict), f"release image {service} must be an object")
        require(
            set(image) == {"repository"},
            f"release image {service} must define only repository",
        )
        repository = image["repository"]
        require(
            isinstance(repository, str)
            and repository.strip() == repository
            and bool(repository),
            f"release image {service} repository must be a non-empty string",
        )
        repositories[service] = repository
    return repositories


def sensitive_fragments(values: Sequence[str]) -> list[str]:
    """Return full and commonly logged credential fragments for redaction."""
    fragments: set[str] = set()
    for value in values:
        if not value:
            continue
        fragments.add(value)
        if len(value) >= 12:
            fragments.add(value[:12])
        if len(value) >= 6:
            fragments.add(value[:6])
        if len(value) >= 4:
            fragments.add(value[-4:])
    return sorted(fragments, key=len, reverse=True)


def redact(text: str, values: Sequence[str]) -> str:
    """Remove credentials and credential fragments from diagnostic text."""
    redacted = text
    for fragment in sensitive_fragments(values):
        redacted = redacted.replace(fragment, "<redacted>")
    return redacted


def run_command(
    command: list[str],
    *,
    cwd: Path,
    sensitive_values: Sequence[str] = (),
    show_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a command, exposing sanitized output only when it fails."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise SmokeError(f"required command is unavailable: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        output = "\n".join(
            part.strip() for part in (error.stdout, error.stderr) if part
        )
        safe_output = redact(output, sensitive_values)
        message = f"command failed: {' '.join(command[:3])}"
        if safe_output:
            message = f"{message}\n{safe_output}"
        raise SmokeError(message) from error
    if show_output:
        safe_output = redact(result.stdout + result.stderr, sensitive_values)
        if safe_output:
            print(safe_output, end="" if safe_output.endswith("\n") else "\n")
    return result


def parse_published_images(
    values: Sequence[str], image_repositories: dict[str, str]
) -> dict[str, PublishedImage]:
    """Parse exact SERVICE=REPOSITORY@DIGEST bindings from CLI input."""
    images: dict[str, PublishedImage] = {}
    for value in values:
        service, separator, reference = value.partition("=")
        repository, digest_separator, digest = reference.rpartition("@")
        require(
            bool(separator and digest_separator),
            "--expected-image must use SERVICE=REPOSITORY@sha256:DIGEST",
        )
        require(service in CORE_SERVICES, f"unknown Studio image service: {service}")
        require(service not in images, f"duplicate expected image for {service}")
        require(
            repository == image_repositories[service],
            f"{service} image repository must be {image_repositories[service]}",
        )
        require(
            DIGEST_PATTERN.fullmatch(digest) is not None,
            f"{service} image digest must be a sha256 digest",
        )
        images[service] = PublishedImage(service, repository, digest)
    require(
        set(images) == set(CORE_SERVICES),
        f"registry smoke requires exact images for {', '.join(CORE_SERVICES)}",
    )
    return images


def parse_environment(path: Path) -> dict[str, str]:
    """Read simple KEY=value assignments from a generated environment file."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", maxsplit=1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def update_environment_value(path: Path, key: str, value: str) -> None:
    """Replace one existing environment assignment without duplicating it."""
    lines = path.read_text(encoding="utf-8").splitlines()
    updated = 0
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("#") and stripped.partition("=")[0].strip() == key:
            output.append(f"{key}={value}")
            updated += 1
        else:
            output.append(line)
    require(updated == 1, f"expected exactly one {key} assignment, found {updated}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def allocate_tcp_ports(count: int) -> tuple[int, ...]:
    """Ask the host for distinct available loopback TCP ports."""
    listeners: list[socket.socket] = []
    try:
        for _ in range(count):
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", 0))
            listeners.append(listener)
        return tuple(int(listener.getsockname()[1]) for listener in listeners)
    finally:
        for listener in listeners:
            listener.close()


def append_runtime_ports(path: Path, ports: dict[str, int]) -> None:
    """Add smoke-only host port overrides to a generated environment file."""
    current = parse_environment(path)
    for key in ports:
        require(key not in current, f"runtime port is already configured: {key}")
    with path.open("a", encoding="utf-8") as environment:
        environment.write("\n# Isolated distribution smoke ports\n")
        for key, port in ports.items():
            environment.write(f"{key}={port}\n")


def remote_manifest_digest(output: str) -> str:
    """Extract the top-level manifest digest from Buildx inspection output."""
    for line in output.splitlines():
        if line.startswith("Digest:"):
            digest = line.partition(":")[2].strip()
            require(
                DIGEST_PATTERN.fullmatch(digest) is not None,
                "registry returned an invalid image digest",
            )
            return digest
    raise SmokeError("registry inspection did not return a manifest digest")


def assert_compose_images(
    rendered: dict[str, Any], version: str, image_repositories: dict[str, str]
) -> None:
    """Prove the distribution starts only the exact version-tagged Studio images."""
    services = rendered.get("services")
    require(isinstance(services, dict), "Compose services must render as an object")
    for service, compose_service in zip(CORE_SERVICES, COMPOSE_CORE_SERVICES, strict=True):
        config = services.get(compose_service)
        require(isinstance(config, dict), f"Compose service is missing: {compose_service}")
        expected = f"{image_repositories[service]}:{version}"
        require(
            config.get("image") == expected,
            f"{compose_service} must use exact image {expected}",
        )
        require("build" not in config, f"{compose_service} must not build a fallback image")


def assert_compose_exact_images(
    rendered: dict[str, Any], expected_images: dict[str, PublishedImage]
) -> None:
    """Prove the effective smoke runtime uses only evidence-bound digests."""
    services = rendered.get("services")
    require(isinstance(services, dict), "Compose services must render as an object")
    for service, compose_service in zip(CORE_SERVICES, COMPOSE_CORE_SERVICES, strict=True):
        config = services.get(compose_service)
        require(isinstance(config, dict), f"Compose service is missing: {compose_service}")
        expected = expected_images[service]
        exact_reference = f"{expected.repository}@{expected.digest}"
        require(
            config.get("image") == exact_reference,
            f"{compose_service} must use exact image {exact_reference}",
        )


class JsonClient:
    """Small JSON client that preserves the Studio authentication cookie."""

    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar)
        )
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def request(
        self, path: str, *, method: str = "GET", body: dict[str, str] | None = None
    ) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                payload = response.read()
        except (urllib.error.URLError, OSError) as error:
            raise SmokeError(f"Studio API request failed: {method} {path}") from error
        if not payload:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError as error:
            raise SmokeError(f"Studio API returned invalid JSON: {method} {path}") from error


class StudioDistributionSmoke:
    """Own the lifecycle of one isolated VM distribution smoke deployment."""

    def __init__(
        self,
        *,
        repository_root: Path,
        studio_version: str,
        image_source: str,
        platform: str,
        expected_images: dict[str, PublishedImage],
        image_repositories: dict[str, str],
        timeout_seconds: int,
    ) -> None:
        self.repository_root = repository_root
        self.studio_root = repository_root / "apps/studio"
        self.distribution_source = self.studio_root / "deployments/vm-caddy"
        self.studio_version = studio_version
        self.image_source = image_source
        self.platform = platform
        self.expected_images = expected_images
        self.image_repositories = image_repositories
        self.timeout_seconds = timeout_seconds
        self.project_name = f"junjo-smoke-{secrets.token_hex(6)}"
        self.runtime_root: Path | None = None
        self.exact_image_override: Path | None = None
        self.sensitive_values: list[str] = []
        self.started = False
        (
            self.frontend_port,
            self.backend_port,
            self.ingestion_port,
        ) = allocate_tcp_ports(3)

    def compose_command(self, *arguments: str) -> list[str]:
        command = ["docker", "compose", "--project-name", self.project_name]
        if self.exact_image_override is not None:
            command.extend(
                [
                    "--file",
                    "docker-compose.yml",
                    "--file",
                    str(self.exact_image_override),
                ]
            )
        return [*command, *arguments]

    def write_exact_image_override(self) -> None:
        """Bind the smoke runtime to the three evidence digests, never mutable tags."""
        require(self.runtime_root is not None, "runtime has not been prepared")
        require(
            set(self.expected_images) == set(CORE_SERVICES),
            "registry smoke requires an exact image for every core service",
        )
        services = {}
        for service, compose_service in zip(
            CORE_SERVICES, COMPOSE_CORE_SERVICES, strict=True
        ):
            expected = self.expected_images[service]
            services[compose_service] = {
                "image": f"{expected.repository}@{expected.digest}"
            }
        override = self.runtime_root / EXACT_IMAGE_OVERRIDE
        override.write_text(
            json.dumps({"services": services}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.exact_image_override = override

    def prepare_runtime(self, temporary_root: Path) -> None:
        self.runtime_root = temporary_root / "vm-caddy"
        shutil.copytree(self.distribution_source, self.runtime_root)
        setup = run_command(
            [
                sys.executable,
                str(self.runtime_root / "scripts/junjo"),
                "setup",
                "--non-interactive",
                "--env",
                "development",
                "--profile",
                "4g",
            ],
            cwd=self.runtime_root,
        )
        require(setup.returncode == 0, "development setup failed")
        environment = parse_environment(self.runtime_root / ".env")
        for key in SENSITIVE_ENVIRONMENT_KEYS:
            value = environment.get(key)
            if value and "placeholder" not in value and not value.endswith("_here"):
                self.sensitive_values.append(value)
        append_runtime_ports(
            self.runtime_root / ".env",
            {
                "JUNJO_FRONTEND_HOST_PORT": self.frontend_port,
                "JUNJO_BACKEND_HOST_PORT": self.backend_port,
                "JUNJO_INGESTION_HOST_PORT": self.ingestion_port,
            },
        )

        rendered_result = run_command(
            self.compose_command("config", "--format", "json"),
            cwd=self.runtime_root,
            sensitive_values=self.sensitive_values,
        )
        try:
            rendered = json.loads(rendered_result.stdout)
        except json.JSONDecodeError as error:
            raise SmokeError("Docker Compose returned invalid JSON") from error
        assert_compose_images(rendered, self.studio_version, self.image_repositories)
        if self.image_source == "registry":
            self.write_exact_image_override()
            exact_result = run_command(
                self.compose_command("config", "--format", "json"),
                cwd=self.runtime_root,
                sensitive_values=self.sensitive_values,
            )
            try:
                exact_rendered = json.loads(exact_result.stdout)
            except json.JSONDecodeError as error:
                raise SmokeError("Docker Compose returned invalid JSON") from error
            assert_compose_exact_images(exact_rendered, self.expected_images)

    def build_local_images(self) -> None:
        for service in CORE_SERVICES:
            image = f"{self.image_repositories[service]}:{self.studio_version}"
            print(f"Building local Studio {service} image {image}.", flush=True)
            run_command(
                [
                    "docker",
                    "build",
                    "--platform",
                    self.platform,
                    "--target",
                    "production",
                    "--tag",
                    image,
                    "--file",
                    str(self.studio_root / service / "Dockerfile"),
                    str(self.studio_root),
                ],
                cwd=self.repository_root,
            )
            run_command(
                ["docker", "image", "inspect", image], cwd=self.repository_root
            )

    def pull_exact_registry_images(self) -> None:
        for service in CORE_SERVICES:
            expected = self.expected_images[service]
            tagged_image = f"{expected.repository}:{self.studio_version}"
            inspection = run_command(
                ["docker", "buildx", "imagetools", "inspect", tagged_image],
                cwd=self.repository_root,
            )
            actual_digest = remote_manifest_digest(inspection.stdout)
            require(
                actual_digest == expected.digest,
                f"{tagged_image} resolves to {actual_digest}, expected {expected.digest}",
            )
            print(f"Pulling exact published Studio {service} image.", flush=True)
            exact_image = f"{expected.repository}@{expected.digest}"
            run_command(
                ["docker", "pull", "--platform", self.platform, exact_image],
                cwd=self.repository_root,
            )

    def build_distribution_images(self) -> None:
        require(self.runtime_root is not None, "runtime has not been prepared")
        print("Building VM/Caddy distribution images.", flush=True)
        run_command(
            self.compose_command("build", "caddy", "junjo-app"),
            cwd=self.runtime_root,
            sensitive_values=self.sensitive_values,
        )

    def wait_for_core_services(self) -> None:
        require(self.runtime_root is not None, "runtime has not been prepared")
        deadline = time.monotonic() + self.timeout_seconds
        client = JsonClient(
            f"http://127.0.0.1:{self.backend_port}", timeout_seconds=3
        )
        while time.monotonic() < deadline:
            backend_ready = False
            frontend_ready = False
            ingestion_ready = False
            try:
                health = client.request("/health")
                backend_ready = isinstance(health, dict) and health.get("status") == "ok"
            except SmokeError:
                pass
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.frontend_port}/", timeout=3
                ) as response:
                    frontend_ready = 200 <= response.status < 400
            except (urllib.error.URLError, OSError):
                pass
            ingestion = subprocess.run(
                self.compose_command(
                    "exec",
                    "-T",
                    "junjo-ai-studio-ingestion",
                    "/bin/grpc_health_probe",
                    "-addr=localhost:50052",
                ),
                cwd=self.runtime_root,
                check=False,
                capture_output=True,
                text=True,
            )
            ingestion_ready = ingestion.returncode == 0
            if backend_ready and frontend_ready and ingestion_ready:
                return
            time.sleep(3)
        raise SmokeError("Studio core services did not become healthy before timeout")

    def create_api_key(self) -> str:
        email = f"smoke-{secrets.token_hex(8)}@example.com"
        password = secrets.token_urlsafe(32)
        self.sensitive_values.extend([password])
        client = JsonClient(
            f"http://127.0.0.1:{self.backend_port}", timeout_seconds=10
        )
        response = client.request(
            "/users/create-first-user",
            method="POST",
            body={"email": email, "password": password},
        )
        require(isinstance(response, dict), "first-user response must be an object")
        created = client.request(
            "/api_keys", method="POST", body={"name": "Distribution smoke"}
        )
        require(isinstance(created, dict), "API-key response must be an object")
        api_key = created.get("key")
        require(
            isinstance(api_key, str) and len(api_key) >= 32,
            "Studio did not return a valid API key",
        )
        self.sensitive_values.append(api_key)
        return api_key

    def start_demo_application(self, api_key: str) -> None:
        require(self.runtime_root is not None, "runtime has not been prepared")
        update_environment_value(
            self.runtime_root / ".env", "JUNJO_AI_STUDIO_API_KEY", api_key
        )
        run_command(
            self.compose_command(
                "up",
                "--detach",
                "--no-build",
                "--no-deps",
                "--force-recreate",
                "--pull",
                "never",
                "junjo-app",
            ),
            cwd=self.runtime_root,
            sensitive_values=self.sensitive_values,
        )

    def wait_for_example_workflow(self) -> None:
        service_path = urllib.parse.quote(DEMO_SERVICE_NAME, safe="")
        client = JsonClient(
            f"http://127.0.0.1:{self.backend_port}", timeout_seconds=5
        )
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            try:
                services = client.request("/api/v1/observability/services")
                workflows = client.request(
                    f"/api/v1/observability/services/{service_path}/workflows?limit=10"
                )
                if (
                    isinstance(services, list)
                    and DEMO_SERVICE_NAME in services
                    and isinstance(workflows, list)
                    and any(
                        isinstance(workflow, dict)
                        and workflow.get("name") == DEMO_WORKFLOW_NAME
                        for workflow in workflows
                    )
                ):
                    return
            except SmokeError:
                pass
            time.sleep(3)
        raise SmokeError("the real example workflow did not become queryable before timeout")

    def start_core_services(self) -> None:
        require(self.runtime_root is not None, "runtime has not been prepared")
        run_command(
            self.compose_command(
                "up",
                "--detach",
                "--no-build",
                "--pull",
                "never",
                *COMPOSE_CORE_SERVICES,
            ),
            cwd=self.runtime_root,
            sensitive_values=self.sensitive_values,
        )
        self.started = True

    def print_failure_logs(self) -> None:
        if not self.started or self.runtime_root is None:
            return
        try:
            result = subprocess.run(
                self.compose_command("logs", "--no-color", "--timestamps"),
                cwd=self.runtime_root,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            safe_error = redact(str(error), self.sensitive_values)
            print(f"Could not collect Studio smoke logs: {safe_error}", file=sys.stderr)
            return
        output = redact(result.stdout + result.stderr, self.sensitive_values)
        if output:
            print("Sanitized Studio smoke logs:", file=sys.stderr)
            print(output, file=sys.stderr)

    def cleanup(self) -> SmokeError | None:
        """Attempt complete Compose cleanup and return a sanitized failure."""
        if self.runtime_root is None:
            return None
        try:
            result = subprocess.run(
                self.compose_command(
                    "down",
                    "--volumes",
                    "--remove-orphans",
                    "--rmi",
                    "local",
                    "--timeout",
                    "10",
                ),
                cwd=self.runtime_root,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            safe_error = redact(str(error), self.sensitive_values)
            return SmokeError(f"Studio smoke cleanup could not run: {safe_error}")
        if result.returncode != 0:
            output = redact(result.stdout + result.stderr, self.sensitive_values)
            message = "Studio smoke cleanup failed"
            if output:
                message = f"{message}:\n{output}"
            return SmokeError(message)
        return None

    def execute(self) -> None:
        with tempfile.TemporaryDirectory(prefix=f"{self.project_name}-") as directory:
            primary_error: BaseException | None = None
            try:
                self.prepare_runtime(Path(directory))
                if self.image_source == "local":
                    self.build_local_images()
                else:
                    self.pull_exact_registry_images()
                self.build_distribution_images()
                self.start_core_services()
                self.wait_for_core_services()
                api_key = self.create_api_key()
                self.start_demo_application(api_key)
                self.wait_for_example_workflow()
            except BaseException as error:
                primary_error = error
                try:
                    self.print_failure_logs()
                except Exception as diagnostic_error:
                    safe_error = redact(
                        str(diagnostic_error), self.sensitive_values
                    )
                    print(
                        f"Could not collect Studio smoke logs: {safe_error}",
                        file=sys.stderr,
                    )
            try:
                cleanup_error = self.cleanup()
            except Exception as error:
                safe_error = redact(str(error), self.sensitive_values)
                cleanup_error = SmokeError(
                    f"Studio smoke cleanup raised unexpectedly: {safe_error}"
                )
            if primary_error is not None:
                if cleanup_error is None:
                    print("Studio smoke resources were cleaned up.", file=sys.stderr)
                else:
                    print(
                        f"Cleanup also failed after the primary smoke failure:\n{cleanup_error}",
                        file=sys.stderr,
                    )
                raise primary_error
            if cleanup_error is not None:
                raise cleanup_error
            print(
                "Studio distribution smoke passed: the example workflow is queryable, "
                "and all smoke resources were cleaned up.",
                flush=True,
            )


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit local-or-registry smoke-test interface."""
    parser = argparse.ArgumentParser(
        description=(
            "Build or pull exact Studio images, run the VM distribution, send a real "
            "Junjo workflow, query it through Studio, and clean up all runtime resources."
        )
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=DEFAULT_REPOSITORY_ROOT,
        help="Junjo repository root (default: inferred from this script).",
    )
    parser.add_argument("--studio-version", required=True)
    parser.add_argument(
        "--image-source", choices=("local", "registry"), required=True
    )
    parser.add_argument("--platform", default="linux/amd64")
    parser.add_argument(
        "--expected-image",
        action="append",
        default=[],
        metavar="SERVICE=REPOSITORY@DIGEST",
        help="Required three times in registry mode; forbidden in local mode.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=300)
    return parser


def main() -> int:
    """Validate arguments and execute one complete distribution smoke proof."""
    args = build_parser().parse_args()
    require(
        VERSION_PATTERN.fullmatch(args.studio_version) is not None,
        "--studio-version must be a stable X.Y.Z version",
    )
    require(args.timeout_seconds > 0, "--timeout-seconds must be positive")
    repository_root = args.repository_root.resolve()
    require(
        (repository_root / "apps/studio/VERSION").is_file(),
        f"Studio source is missing beneath {repository_root}",
    )
    committed_version = (
        repository_root / "apps/studio/VERSION"
    ).read_text(encoding="utf-8").strip()
    require(
        committed_version == args.studio_version,
        f"requested Studio {args.studio_version} does not match committed {committed_version}",
    )
    image_repositories = load_image_repositories(repository_root)
    if args.image_source == "registry":
        expected_images = parse_published_images(args.expected_image, image_repositories)
    else:
        require(
            not args.expected_image,
            "--expected-image is valid only with --image-source registry",
        )
        expected_images = {}

    smoke = StudioDistributionSmoke(
        repository_root=repository_root,
        studio_version=args.studio_version,
        image_source=args.image_source,
        platform=args.platform,
        expected_images=expected_images,
        image_repositories=image_repositories,
        timeout_seconds=args.timeout_seconds,
    )
    smoke.execute()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
