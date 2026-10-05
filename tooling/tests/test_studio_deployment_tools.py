"""Offline tests for Studio deployment validation and export tooling."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from email.message import Message
from unittest import mock
from pathlib import Path
from types import ModuleType
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def load_script_module(name: str, relative_path: str) -> ModuleType:
    """Load a repository script as a module without making tooling a package."""
    path = REPOSITORY_ROOT / relative_path
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


validator = load_script_module(
    "validate_studio_deployments",
    "tooling/scripts/validate_studio_deployments.py",
)
exporter = load_script_module(
    "export_studio_distribution",
    "tooling/scripts/export_studio_distribution.py",
)
smoke = load_script_module(
    "smoke_studio_distribution",
    "tooling/scripts/smoke_studio_distribution.py",
)
SMOKE_IMAGE_REPOSITORIES = smoke.load_image_repositories(REPOSITORY_ROOT)


def core_service(image: str, port: int) -> dict[str, object]:
    """Build the common rendered Compose fields used by test fixtures."""
    return {
        "image": image,
        "ports": [{"target": port, "published": str(port), "protocol": "tcp"}],
        "networks": {"junjo-network": None},
    }


def rendered_compose(distribution_name: str, version: str = "1.2.3") -> dict[str, Any]:
    """Build a valid rendered Compose fixture for one distribution contract."""
    app = core_service(f"mdrideout/junjo-ai-studio-app:{version}", 26154)
    app["environment"] = {
        "INGESTION_HOST": validator.INGESTION,
        "INGESTION_PORT": "50052",
        "PORT": "26154",
        "GRPC_PORT": "50053",
        "JUNJO_SQLITE_PATH": "/app/.dbdata/sqlite/junjo.db",
        "JUNJO_METADATA_DB_PATH": "/app/.dbdata/sqlite/metadata.db",
        "JUNJO_PARQUET_STORAGE_PATH": "/app/.dbdata/spans/parquet",
    }
    app["volumes"] = [{"source": "/fixture/data", "target": "/app/.dbdata"}]

    ingestion = core_service(f"mdrideout/junjo-ai-studio-ingestion:{version}", 26155)
    ingestion["environment"] = {
        "BACKEND_GRPC_HOST": validator.APP,
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
    }
    ingestion["volumes"] = [{"source": "/fixture/data", "target": "/app/.dbdata"}]
    ingestion["depends_on"] = {validator.APP: {"condition": "service_started"}}
    ingestion["healthcheck"] = {
        "test": ["CMD", "/bin/grpc_health_probe", "-addr=localhost:50052"],
        "timeout": "3s",
        "interval": "5s",
        "retries": 5,
        "start_period": "30s",
    }

    services: dict[str, Any] = {
        validator.APP: app,
        validator.INGESTION: ingestion,
    }
    rendered: dict[str, Any] = {
        "services": services,
        "networks": {
            "junjo-network": {
                "name": "junjo-fixture-validation_junjo-network",
                "driver": "bridge",
                "ipam": {},
            }
        },
    }

    if distribution_name == "vm-caddy":
        services["example-app"] = {
            "build": {"context": "/fixture/junjo_app", "dockerfile": "Dockerfile"},
            "depends_on": {validator.INGESTION: {"condition": "service_started"}},
            "networks": {"junjo-network": None},
        }
        services["caddy"] = {
            "build": {"context": "/fixture/caddy", "dockerfile": "Dockerfile"},
            "depends_on": {
                validator.APP: {"condition": "service_started"},
            },
            "networks": {"junjo-network": None},
            "ports": [
                {"target": 80, "published": "80", "protocol": "tcp"},
                {"target": 443, "published": "443", "protocol": "tcp"},
                {"target": 443, "published": "443", "protocol": "udp"},
            ],
        }
        rendered["volumes"] = {"caddy_data": {}}
    return rendered


class DeploymentComposeContractTests(unittest.TestCase):
    """Exercise topology validation without running containers or pulling images."""

    def test_minimal_contract_accepts_only_the_two_core_services(self) -> None:
        distribution = next(
            item for item in validator.DISTRIBUTIONS if item.name == "minimal"
        )
        validator.validate_rendered_compose(
            distribution, rendered_compose("minimal"), "1.2.3", Path("/fixture")
        )
        rendered = rendered_compose("minimal")
        rendered["services"]["third-service"] = core_service(
            "example.invalid/third-service:1.2.3", 9999
        )
        with self.assertRaisesRegex(RuntimeError, "expected services"):
            validator.validate_rendered_compose(
                distribution, rendered, "1.2.3", Path("/fixture")
            )

    def test_vm_caddy_contract_requires_the_operator_services(self) -> None:
        distribution = next(
            item for item in validator.DISTRIBUTIONS if item.name == "vm-caddy"
        )
        validator.validate_rendered_compose(
            distribution, rendered_compose("vm-caddy"), "1.2.3", Path("/fixture")
        )

    def test_image_pin_must_exactly_match_studio_version(self) -> None:
        distribution = next(
            item for item in validator.DISTRIBUTIONS if item.name == "minimal"
        )
        rendered = rendered_compose("minimal")
        rendered["services"][validator.APP]["image"] = (
            "mdrideout/junjo-ai-studio-app:latest"
        )
        with self.assertRaisesRegex(RuntimeError, "image pins must exactly match"):
            validator.validate_rendered_compose(
                distribution, rendered, "1.2.3", Path("/fixture")
            )

    def test_ingestion_healthcheck_must_use_internal_listener(self) -> None:
        distribution = next(
            item for item in validator.DISTRIBUTIONS if item.name == "minimal"
        )
        rendered = rendered_compose("minimal")
        rendered["services"][validator.INGESTION]["healthcheck"] = {
            "test": ["CMD", "probe", "localhost:26155"]
        }
        with self.assertRaisesRegex(RuntimeError, "healthcheck must be exactly"):
            validator.validate_rendered_compose(
                distribution, rendered, "1.2.3", Path("/fixture")
            )

    def test_internal_ports_must_not_be_published(self) -> None:
        distribution = next(
            item for item in validator.DISTRIBUTIONS if item.name == "minimal"
        )
        rendered = rendered_compose("minimal")
        rendered["services"][validator.APP]["ports"].append(
            {"target": 50053, "published": "50053", "protocol": "tcp"}
        )
        with self.assertRaisesRegex(RuntimeError, "ports must be exactly"):
            validator.validate_rendered_compose(
                distribution, rendered, "1.2.3", Path("/fixture")
            )

    def test_core_services_must_not_add_build_contexts(self) -> None:
        distribution = next(
            item for item in validator.DISTRIBUTIONS if item.name == "minimal"
        )
        rendered = rendered_compose("minimal")
        rendered["services"][validator.APP]["build"] = {"context": "/fixture/backend"}
        with self.assertRaisesRegex(RuntimeError, "must use only its pinned image"):
            validator.validate_rendered_compose(
                distribution, rendered, "1.2.3", Path("/fixture")
            )

    def test_services_must_not_escape_compose_project_namespacing(self) -> None:
        distribution = next(
            item for item in validator.DISTRIBUTIONS if item.name == "minimal"
        )
        rendered = rendered_compose("minimal")
        rendered["services"][validator.APP]["container_name"] = "fixed-app"
        with self.assertRaisesRegex(RuntimeError, "project-scoped container name"):
            validator.validate_rendered_compose(
                distribution, rendered, "1.2.3", Path("/fixture")
            )

    def test_network_must_be_scoped_to_the_compose_project(self) -> None:
        distribution = next(
            item for item in validator.DISTRIBUTIONS if item.name == "minimal"
        )
        rendered = rendered_compose("minimal")
        rendered["networks"]["junjo-network"]["name"] = "junjo_network"
        with self.assertRaisesRegex(RuntimeError, "project-scoped"):
            validator.validate_rendered_compose(
                distribution, rendered, "1.2.3", Path("/fixture")
            )


class DistributionSmokeContractTests(unittest.TestCase):
    """Exercise exact-image, redaction, and environment smoke contracts offline."""

    def test_registry_images_bind_every_service_repository_and_digest(self) -> None:
        digest = "sha256:" + ("a" * 64)
        arguments = [
            f"{service}={repository}@{digest}"
            for service, repository in SMOKE_IMAGE_REPOSITORIES.items()
        ]
        images = smoke.parse_published_images(arguments, SMOKE_IMAGE_REPOSITORIES)
        self.assertEqual(set(images), set(smoke.CORE_SERVICES))
        for service, image in images.items():
            self.assertEqual(image.repository, SMOKE_IMAGE_REPOSITORIES[service])
            self.assertEqual(image.digest, digest)

    def test_registry_images_reject_missing_or_wrong_repository_bindings(self) -> None:
        digest = "sha256:" + ("a" * 64)
        with self.assertRaisesRegex(smoke.SmokeError, "requires exact images"):
            smoke.parse_published_images(
                [f"backend={SMOKE_IMAGE_REPOSITORIES['backend']}@{digest}"],
                SMOKE_IMAGE_REPOSITORIES,
            )
        with self.assertRaisesRegex(smoke.SmokeError, "repository must be"):
            smoke.parse_published_images(
                [
                    f"backend=example.invalid/backend@{digest}",
                    f"ingestion={SMOKE_IMAGE_REPOSITORIES['ingestion']}@{digest}",
                ],
                SMOKE_IMAGE_REPOSITORIES,
            )

    def test_compose_images_must_exactly_match_requested_version(self) -> None:
        rendered = rendered_compose("vm-caddy", version="1.2.3")
        smoke.assert_compose_images(rendered, "1.2.3", SMOKE_IMAGE_REPOSITORIES)
        rendered["services"][validator.APP]["image"] = (
            "mdrideout/junjo-ai-studio-app:latest"
        )
        with self.assertRaisesRegex(smoke.SmokeError, "must use exact image"):
            smoke.assert_compose_images(rendered, "1.2.3", SMOKE_IMAGE_REPOSITORIES)

    def test_registry_runtime_override_binds_digests_and_named_storage(self) -> None:
        digest = "sha256:" + ("c" * 64)
        expected_images = self.expected_registry_images(digest)
        runner = self.registry_runner(expected_images)
        with tempfile.TemporaryDirectory(prefix="junjo-exact-images-") as directory:
            runner.runtime_root = Path(directory)
            runner.write_runtime_override()
            self.assertIsNotNone(runner.runtime_override)
            override = json.loads(runner.runtime_override.read_text(encoding="utf-8"))
            for service, compose_service in zip(
                smoke.CORE_SERVICES, smoke.COMPOSE_CORE_SERVICES, strict=True
            ):
                expected = expected_images[service]
                self.assertEqual(
                    override["services"][compose_service]["image"],
                    f"{expected.repository}@{expected.digest}",
                )
            smoke.assert_smoke_named_storage(override, runner.data_volume_name)
            command = runner.compose_command("up", "--detach")
            self.assertIn("docker-compose.yml", command)
            self.assertIn(str(runner.runtime_override), command)

    def test_local_runtime_override_uses_project_owned_named_storage(self) -> None:
        runner = self.smoke_runner()
        with tempfile.TemporaryDirectory(prefix="junjo-local-smoke-") as directory:
            runner.runtime_root = Path(directory)
            runner.write_runtime_override()
            self.assertIsNotNone(runner.runtime_override)
            override = json.loads(runner.runtime_override.read_text(encoding="utf-8"))
            smoke.assert_smoke_named_storage(override, runner.data_volume_name)
            self.assertTrue(
                all(
                    "image" not in override["services"][service]
                    for service in smoke.COMPOSE_CORE_SERVICES
                )
            )

    def test_runtime_override_keeps_session_cookies_usable_over_http(self) -> None:
        runner = self.smoke_runner()
        with tempfile.TemporaryDirectory(prefix="junjo-session-smoke-") as directory:
            runner.runtime_root = Path(directory)
            runner.write_runtime_override()
            self.assertIsNotNone(runner.runtime_override)
            override = json.loads(runner.runtime_override.read_text(encoding="utf-8"))

        smoke.assert_smoke_session_mode(override)
        app = override["services"]["junjo-ai-studio-app"]
        self.assertEqual(app["environment"], {"JUNJO_ENV": "development"})
        app["environment"]["JUNJO_ENV"] = "production"
        with self.assertRaisesRegex(smoke.SmokeError, "development-mode HTTP cookies"):
            smoke.assert_smoke_session_mode(override)

    def app_response(self) -> mock.MagicMock:
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.headers.get_content_type.return_value = "text/html"
        return response

    def health_response(self) -> mock.MagicMock:
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"status": "ok"}'
        return response

    def not_found_error(self, payload: bytes) -> Exception:
        error = smoke.urllib.error.HTTPError(
            "http://fixture.invalid", 404, "Not Found", Message(), io.BytesIO(payload)
        )
        self.addCleanup(error.close)
        return error

    def test_live_studio_origin_serves_app_health_and_api_error_body(self) -> None:
        runner = self.smoke_runner()
        with mock.patch.object(
            smoke.urllib.request,
            "urlopen",
            side_effect=[
                self.app_response(),
                self.health_response(),
                self.not_found_error(b'{"code": "not_found", "message": "Not found"}'),
            ],
        ) as urlopen:
            runner.assert_live_studio_origin()

        self.assertTrue(smoke.UNKNOWN_API_PATH.startswith("/api/"))
        self.assertEqual(
            [call.args[0] for call in urlopen.call_args_list],
            [
                f"{runner.studio_origin}/",
                f"{runner.studio_origin}/health",
                f"{runner.studio_origin}{smoke.UNKNOWN_API_PATH}",
            ],
        )

    def test_live_studio_origin_rejects_a_missing_app_or_a_swallowed_api_path(
        self,
    ) -> None:
        runner = self.smoke_runner()
        json_at_root = self.app_response()
        json_at_root.headers.get_content_type.return_value = "application/json"
        cases = (
            (
                [self.not_found_error(b'{"code": "not_found"}')],
                "does not serve the app at /",
            ),
            ([json_at_root], "does not serve the app as HTML at /"),
            (
                [self.app_response(), self.health_response(), self.app_response()],
                "as if it existed",
            ),
            (
                [
                    self.app_response(),
                    self.health_response(),
                    self.not_found_error(b"<!doctype html>"),
                ],
                "without the JSON error body",
            ),
        )
        for responses, message in cases:
            with (
                self.subTest(message=message),
                mock.patch.object(
                    smoke.urllib.request, "urlopen", side_effect=responses
                ),
                self.assertRaisesRegex(smoke.SmokeError, message),
            ):
                runner.assert_live_studio_origin()

    def test_registry_pull_uses_evidence_digest_instead_of_version_tag(self) -> None:
        digest = "sha256:" + ("d" * 64)
        expected_images = self.expected_registry_images(digest)
        runner = self.registry_runner(expected_images)
        commands: list[list[str]] = []

        def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            stdout = (
                f"Name: fixture\nDigest: {digest}\n" if "imagetools" in command else ""
            )
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        with mock.patch.object(smoke, "run_command", side_effect=run):
            runner.pull_exact_registry_images()

        pull_commands = [command for command in commands if command[1] == "pull"]
        self.assertEqual(len(pull_commands), len(smoke.CORE_SERVICES))
        self.assertEqual(
            {command[-1] for command in pull_commands},
            {
                f"{image.repository}@{image.digest}"
                for image in expected_images.values()
            },
        )

    def test_manifest_inspection_requires_a_valid_top_level_digest(self) -> None:
        digest = "sha256:" + ("b" * 64)
        output = f"Name: fixture\nMediaType: application/test\nDigest: {digest}\n"
        self.assertEqual(smoke.remote_manifest_digest(output), digest)
        with self.assertRaisesRegex(smoke.SmokeError, "did not return"):
            smoke.remote_manifest_digest("Name: fixture\n")

    def test_diagnostics_redact_full_credentials_and_logged_fragments(self) -> None:
        credential = "credential-value-with-enough-entropy"
        diagnostic = (
            f"full={credential} prefix={credential[:12]} short={credential[:6]} "
            f"suffix={credential[-4:]}"
        )
        redacted = smoke.redact(diagnostic, [credential])
        self.assertNotIn(credential, redacted)
        self.assertNotIn(credential[:12], redacted)
        self.assertNotIn(credential[:6], redacted)
        self.assertNotIn(credential[-4:], redacted)

    def test_api_key_update_replaces_one_existing_assignment(self) -> None:
        with tempfile.TemporaryDirectory(prefix="junjo-smoke-env-test-") as directory:
            environment = Path(directory) / ".env"
            environment.write_text(
                "JUNJO_ENV=development\nJUNJO_AI_STUDIO_API_KEY=placeholder\n",
                encoding="utf-8",
            )
            smoke.update_environment_value(
                environment, "JUNJO_AI_STUDIO_API_KEY", "replacement"
            )
            text = environment.read_text(encoding="utf-8")
            self.assertEqual(text.count("JUNJO_AI_STUDIO_API_KEY="), 1)
            self.assertIn("JUNJO_AI_STUDIO_API_KEY=replacement", text)

    def smoke_runner(self) -> Any:
        return smoke.StudioDistributionSmoke(
            repository_root=REPOSITORY_ROOT,
            studio_version=(REPOSITORY_ROOT / "apps/studio/VERSION")
            .read_text(encoding="utf-8")
            .strip(),
            image_source="local",
            platform="linux/amd64",
            expected_images={},
            image_repositories=SMOKE_IMAGE_REPOSITORIES,
            timeout_seconds=1,
            evidence_directory=Path("/tmp/junjo-studio-smoke-tests"),
        )

    def expected_registry_images(self, digest: str) -> dict[str, smoke.PublishedImage]:
        return {
            service: smoke.PublishedImage(service, repository, digest)
            for service, repository in SMOKE_IMAGE_REPOSITORIES.items()
        }

    def registry_runner(self, expected_images: dict[str, smoke.PublishedImage]) -> Any:
        return smoke.StudioDistributionSmoke(
            repository_root=REPOSITORY_ROOT,
            studio_version=(REPOSITORY_ROOT / "apps/studio/VERSION")
            .read_text(encoding="utf-8")
            .strip(),
            image_source="registry",
            platform="linux/amd64",
            expected_images=expected_images,
            image_repositories=SMOKE_IMAGE_REPOSITORIES,
            timeout_seconds=1,
            evidence_directory=Path("/tmp/junjo-studio-smoke-tests"),
        )

    def test_agent_studio_proof_keeps_credentials_out_of_commands_and_artifacts(
        self,
    ) -> None:
        runner = self.smoke_runner()
        identity = smoke.SmokeIdentity(
            email="smoke-user@example.com",
            password="smoke-password-with-entropy",
            api_key="k" * 40,
        )
        calls: list[tuple[list[str], dict[str, object]]] = []

        def run(
            command: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            calls.append((command, kwargs))
            if any(item.endswith("validate_agent_studio_e2e.py") for item in command):
                output = Path(command[command.index("--evidence-output") + 1])
                output.write_text('{"schema_version": 1}\n', encoding="utf-8")
            if "test:e2e:agent-live" in command:
                output = Path(command[command.index("--screenshot") + 1])
                output.write_bytes(b"png fixture")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory(prefix="junjo-h2-smoke-") as directory:
            runner.evidence_directory = Path(directory)
            with mock.patch.object(smoke, "run_command", side_effect=run):
                runner.run_agent_studio_proof(identity)
            manifest = json.loads(
                (runner.evidence_directory / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(len(calls), 2)
        for command, kwargs in calls:
            rendered = " ".join(command)
            self.assertNotIn(identity.email, rendered)
            self.assertNotIn(identity.password, rendered)
            self.assertNotIn(identity.api_key, rendered)
            self.assertEqual(
                kwargs["environment"],
                {
                    "JUNJO_STUDIO_E2E_EXISTING_EMAIL": identity.email,
                    "JUNJO_STUDIO_E2E_EXISTING_PASSWORD": identity.password,
                },
            )
        self.assertEqual(
            set(manifest["artifacts"]),
            {"agent-evidence.json", "agent-diagnostics.png"},
        )
        self.assert_one_studio_origin(calls, runner, "test:e2e:agent-live")

    def test_evaluation_studio_proof_extends_manifest_without_exposing_credentials(
        self,
    ) -> None:
        runner = self.smoke_runner()
        identity = smoke.SmokeIdentity(
            email="smoke-user@example.com",
            password="smoke-password-with-entropy",
            api_key="k" * 40,
        )
        calls: list[tuple[list[str], dict[str, object]]] = []

        def run(
            command: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            calls.append((command, kwargs))
            if any(
                item.endswith("validate_evaluation_studio_e2e.py") for item in command
            ):
                output = Path(command[command.index("--evidence-output") + 1])
                output.write_text('{"schema_version": 1}\n', encoding="utf-8")
            if "test:e2e:evaluation-live" in command:
                output = Path(command[command.index("--screenshot") + 1])
                output.write_bytes(b"png fixture")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory(prefix="junjo-evaluation-smoke-") as directory:
            runner.evidence_directory = Path(directory)
            manifest_path = runner.evidence_directory / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "studio_version": runner.studio_version,
                        "image_source": runner.image_source,
                        "artifacts": {
                            "agent-evidence.json": {"sha256": "sha256:agent"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(smoke, "run_command", side_effect=run):
                runner.run_evaluation_studio_proof(identity)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(len(calls), 2)
        for command, kwargs in calls:
            rendered = " ".join(command)
            self.assertNotIn(identity.email, rendered)
            self.assertNotIn(identity.password, rendered)
            self.assertNotIn(identity.api_key, rendered)
            self.assertEqual(
                kwargs["environment"],
                {
                    "JUNJO_STUDIO_E2E_EXISTING_EMAIL": identity.email,
                    "JUNJO_STUDIO_E2E_EXISTING_PASSWORD": identity.password,
                },
            )
        self.assertEqual(
            set(manifest["artifacts"]),
            {
                "agent-evidence.json",
                "evaluation-evidence.json",
                "evaluation-runs.png",
            },
        )
        self.assert_one_studio_origin(calls, runner, "test:e2e:evaluation-live")

    def assert_one_studio_origin(
        self,
        calls: list[tuple[list[str], dict[str, object]]],
        runner: Any,
        browser_script: str,
    ) -> None:
        """Both proof commands must target the one Studio origin."""
        api_command, browser_command = (command for command, _ in calls)
        self.assertEqual(
            api_command[api_command.index("--backend-url") + 1],
            runner.studio_origin,
        )
        self.assertIn(browser_script, browser_command)
        self.assertEqual(
            browser_command[browser_command.index("--studio-url") + 1],
            runner.studio_origin,
        )
        self.assertNotIn("--backend-url", browser_command)

    def test_example_workflow_query_authenticates_before_protected_requests(
        self,
    ) -> None:
        runner = self.smoke_runner()
        identity = smoke.SmokeIdentity(
            email="smoke-user@example.com",
            password="smoke-password-with-entropy",
            api_key="k" * 40,
        )
        requests: list[tuple[str, str, dict[str, str] | None]] = []

        class FakeJsonClient:
            def __init__(self, base_url: str, timeout_seconds: float) -> None:
                self.base_url = base_url
                self.timeout_seconds = timeout_seconds

            def request(
                self,
                path: str,
                *,
                method: str = "GET",
                body: dict[str, str] | None = None,
            ) -> object:
                requests.append((path, method, body))
                if path == "/api/v1/observability/services":
                    return [smoke.DEMO_SERVICE_NAME]
                if path.endswith("/workflows?limit=10"):
                    return [{"name": smoke.DEMO_WORKFLOW_NAME}]
                return {}

        with mock.patch.object(smoke, "JsonClient", FakeJsonClient):
            runner.wait_for_example_workflow(identity)

        self.assertEqual(
            requests,
            [
                (
                    "/api/v1/sign-in",
                    "POST",
                    {"email": identity.email, "password": identity.password},
                ),
                ("/api/v1/observability/services", "GET", None),
                (
                    "/api/v1/observability/services/Junjo%20Deployment%20Example/workflows?limit=10",
                    "GET",
                    None,
                ),
            ],
        )

    @contextlib.contextmanager
    def mocked_successful_smoke(
        self,
        runner: Any,
        *,
        cleanup_error: Exception | None,
    ) -> Any:
        with contextlib.ExitStack() as stack:
            for method_name in (
                "prepare_runtime",
                "build_local_images",
                "build_distribution_images",
                "start_core_services",
                "wait_for_core_services",
                "start_demo_application",
                "wait_for_example_workflow",
                "run_agent_studio_proof",
                "run_evaluation_studio_proof",
            ):
                stack.enter_context(mock.patch.object(runner, method_name))
            stack.enter_context(
                mock.patch.object(
                    runner,
                    "create_identity",
                    return_value=smoke.SmokeIdentity(
                        email="smoke@example.com",
                        password="test-password",
                        api_key="test-key",
                    ),
                )
            )
            cleanup = stack.enter_context(
                mock.patch.object(runner, "cleanup", return_value=cleanup_error)
            )
            yield cleanup

    def test_cleanup_failure_fails_an_otherwise_successful_smoke(self) -> None:
        runner = self.smoke_runner()
        cleanup_error = smoke.SmokeError("sanitized cleanup failure")
        output = io.StringIO()
        with (
            self.mocked_successful_smoke(
                runner, cleanup_error=cleanup_error
            ) as cleanup,
            contextlib.redirect_stdout(output),
            self.assertRaises(smoke.SmokeError) as raised,
        ):
            runner.execute()
        self.assertIs(raised.exception, cleanup_error)
        cleanup.assert_called_once_with()
        self.assertNotIn("smoke passed", output.getvalue())

    def test_successful_smoke_with_successful_cleanup_returns_normally(self) -> None:
        runner = self.smoke_runner()
        output = io.StringIO()
        with (
            self.mocked_successful_smoke(runner, cleanup_error=None) as cleanup,
            contextlib.redirect_stdout(output),
        ):
            runner.execute()
        cleanup.assert_called_once_with()
        self.assertIn("all smoke resources were cleaned up", output.getvalue())

    def test_cleanup_failure_does_not_mask_the_primary_smoke_failure(self) -> None:
        runner = self.smoke_runner()
        primary_error = smoke.SmokeError("primary smoke failure")
        cleanup_error = smoke.SmokeError("sanitized cleanup failure")
        diagnostics = io.StringIO()
        with (
            mock.patch.object(runner, "prepare_runtime", side_effect=primary_error),
            mock.patch.object(runner, "print_failure_logs"),
            mock.patch.object(runner, "cleanup", return_value=cleanup_error) as cleanup,
            contextlib.redirect_stderr(diagnostics),
            self.assertRaises(smoke.SmokeError) as raised,
        ):
            runner.execute()
        self.assertIs(raised.exception, primary_error)
        cleanup.assert_called_once_with()
        self.assertIn(str(cleanup_error), diagnostics.getvalue())

    def test_cleanup_failure_diagnostics_are_redacted(self) -> None:
        runner = self.smoke_runner()
        credential = "cleanup-secret-with-enough-entropy"
        runner.sensitive_values.append(credential)
        with tempfile.TemporaryDirectory(prefix="junjo-cleanup-test-") as directory:
            runner.runtime_root = Path(directory)
            result = subprocess.CompletedProcess(
                args=["docker", "compose", "down"],
                returncode=1,
                stdout=f"credential={credential}",
                stderr=f"prefix={credential[:12]}",
            )
            with mock.patch.object(smoke.subprocess, "run", return_value=result):
                cleanup_error = runner.cleanup()
        self.assertIsInstance(cleanup_error, smoke.SmokeError)
        diagnostics = str(cleanup_error)
        self.assertNotIn(credential, diagnostics)
        self.assertNotIn(credential[:12], diagnostics)
        self.assertIn("<redacted>", diagnostics)


class DistributionExportTests(unittest.TestCase):
    """Exercise committed-file export, policy rejection, and reproducibility."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="junjo-export-test-"
        )
        self.repository = Path(self.temporary_directory.name) / "repository"
        self.repository.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Junjo Test")
        self.git("config", "user.email", "junjo-test@example.invalid")
        license_text = "Apache License\nVersion 2.0, January 2004\n"
        self.write("LICENSE", license_text)
        self.write("apps/studio/VERSION", "1.2.3\n")
        self.write("apps/studio/deployments/minimal/LICENSE", license_text)
        self.write(
            "apps/studio/deployments/minimal/README.md",
            "# Minimal\n\nApplications that emit Junjo workflow telemetry should use Junjo `4.5.6`.\n",
        )
        compose = (
            REPOSITORY_ROOT / "apps/studio/deployments/minimal/docker-compose.yml"
        ).read_text(encoding="utf-8")
        current_studio_version = (
            (REPOSITORY_ROOT / "apps/studio/VERSION")
            .read_text(encoding="utf-8")
            .strip()
        )
        self.write(
            "apps/studio/deployments/minimal/docker-compose.yml",
            compose.replace(current_studio_version, "1.2.3"),
        )
        env_example = (
            REPOSITORY_ROOT / "apps/studio/deployments/minimal/.env.example"
        ).read_text(encoding="utf-8")
        self.write("apps/studio/deployments/minimal/.env.example", env_example)
        self.write(
            "apps/studio/deployments/minimal/scripts/junjo",
            """#!/usr/bin/env python3
import argparse
parser = argparse.ArgumentParser()
subparsers = parser.add_subparsers(dest="command", required=True)
subparsers.add_parser("setup")
parser.parse_args()
""",
            executable=True,
        )
        self.commit("initial fixture")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def git(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.repository,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def write(
        self, relative_path: str, content: str, *, executable: bool = False
    ) -> None:
        path = self.repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if executable:
            path.chmod(0o755)

    def commit(self, message: str) -> str:
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", message)
        return self.git("rev-parse", "HEAD")

    def export(
        self, name: str, revision: str = "HEAD"
    ) -> tuple[dict[str, object], Path, Path]:
        output = Path(self.temporary_directory.name) / f"{name}-directory"
        archive = Path(self.temporary_directory.name) / f"{name}.tar.gz"
        report = exporter.build_export(
            repository_root=self.repository,
            distribution=exporter.DISTRIBUTIONS["minimal"],
            source_repository="https://github.com/mdrideout/junjo",
            source_revision=revision,
            studio_version="1.2.3",
            compatible_sdk_version="4.5.6",
            output_directory=output,
            archive=archive,
        )
        return report, output, archive

    def test_export_is_reproducible_and_contains_provenance_inventory(self) -> None:
        first_report, first_output, first_archive = self.export("first")
        second_report, _, second_archive = self.export("second")

        self.assertEqual(first_archive.read_bytes(), second_archive.read_bytes())
        self.assertEqual(
            first_report["archive_sha256"], second_report["archive_sha256"]
        )
        self.assertEqual(
            first_report["archive_sha256"],
            hashlib.sha256(first_archive.read_bytes()).hexdigest(),
        )
        manifest = json.loads(
            (first_output / exporter.MANIFEST).read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest["source"]["source_revision"], self.git("rev-parse", "HEAD")
        )
        self.assertEqual(
            manifest["source"]["canonical_source_path"],
            "apps/studio/deployments/minimal",
        )
        inventory_paths = {item["path"] for item in manifest["inventory"]}
        self.assertIn("LICENSE", inventory_paths)
        self.assertIn(exporter.GENERATED_NOTICE, inventory_paths)
        self.assertNotIn(exporter.MANIFEST, inventory_paths)
        self.assertNotIn(str(first_output), json.dumps(manifest))

        with tarfile.open(first_archive, mode="r:gz") as archive_file:
            members = archive_file.getmembers()
        self.assertTrue(members)
        self.assertTrue(all(member.mtime == 0 for member in members))
        self.assertTrue(all(member.uid == 0 and member.gid == 0 for member in members))
        executable = next(
            member for member in members if member.name.endswith("scripts/junjo")
        )
        self.assertEqual(executable.mode, 0o755)

    def test_export_rejects_a_tracked_secret_file(self) -> None:
        self.write("apps/studio/deployments/minimal/.env", "SECRET=unsafe\n")
        revision = self.commit("add forbidden secret")
        with self.assertRaisesRegex(RuntimeError, "unsafe tracked export file .env"):
            self.export("unsafe", revision)

    def test_export_requires_apache_license_in_selected_revision(self) -> None:
        (self.repository / "apps/studio/deployments/minimal/LICENSE").unlink()
        revision = self.commit("remove license")
        with self.assertRaisesRegex(RuntimeError, "tracked LICENSE"):
            self.export("unlicensed", revision)

    def test_export_requires_distribution_license_to_match_root(self) -> None:
        self.write("apps/studio/deployments/minimal/LICENSE", "different license\n")
        revision = self.commit("change distribution license")
        with self.assertRaisesRegex(RuntimeError, "exactly match the root"):
            self.export("wrong-license", revision)

    def test_export_requires_declared_sdk_compatibility_metadata(self) -> None:
        output = Path(self.temporary_directory.name) / "missing-sdk-directory"
        archive = Path(self.temporary_directory.name) / "missing-sdk.tar.gz"
        with self.assertRaisesRegex(RuntimeError, "requires --compatible-sdk-version"):
            exporter.build_export(
                repository_root=self.repository,
                distribution=exporter.DISTRIBUTIONS["minimal"],
                source_repository="https://github.com/mdrideout/junjo",
                source_revision="HEAD",
                studio_version="1.2.3",
                compatible_sdk_version=None,
                output_directory=output,
                archive=archive,
            )

    def test_export_rejects_sdk_metadata_that_differs_from_source(self) -> None:
        self.write(
            "apps/studio/deployments/minimal/README.md",
            "Applications that emit Junjo workflow telemetry should use Junjo `9.9.9`.\n",
        )
        revision = self.commit("change declared SDK version")
        with self.assertRaisesRegex(RuntimeError, "does not match committed"):
            self.export("wrong-sdk", revision)

    def test_export_policy_rejects_secret_runtime_and_cache_paths(self) -> None:
        unsafe_paths = (
            ".env.bak",
            ".env.production",
            "production.env",
            ".dbdata/spans/wal/data",
            ".certs/staging.pem",
            "private/server.key",
            "scripts/__pycache__/setup.pyc",
            "dist/release.zip",
        )
        for unsafe_path in unsafe_paths:
            with self.subTest(path=unsafe_path):
                self.assertIsNotNone(
                    exporter.forbidden_reason(exporter.PurePosixPath(unsafe_path))
                )

    def test_inventory_uses_declared_modes_instead_of_host_stat(self) -> None:
        root = Path(self.temporary_directory.name) / "mode-inventory"
        root.mkdir()
        script = root / "script"
        script.write_text("fixture\n", encoding="utf-8")
        script.chmod(0o600)
        entries = exporter.inventory(root, {"script": 0o755})
        self.assertEqual(entries[0]["mode"], "0755")


if __name__ == "__main__":
    unittest.main()
