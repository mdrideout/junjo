"""Offline behavioral tests for local Studio credential provisioning."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def load_provisioner() -> ModuleType:
    """Load the stdlib-only provisioner without making tooling a package."""

    path = REPOSITORY_ROOT / "tooling/scripts/provision_local_studio.py"
    specification = importlib.util.spec_from_file_location(
        "provision_local_studio",
        path,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


provisioner = load_provisioner()


class FakeStudioClient:
    """Stateful public-API fixture used for idempotence and auth tests."""

    def __init__(
        self,
        *,
        environment: str = "development",
        users_exist: bool = False,
        allow_sign_in: bool = True,
    ) -> None:
        self.environment = environment
        self.users_exist = users_exist
        self.allow_sign_in = allow_sign_in
        self.authenticated = False
        self.api_keys: list[dict[str, object]] = []
        self.access_tokens: list[dict[str, object]] = []
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: dict[str, object] | None = None,
    ) -> Any:
        self.calls.append((path, method, body))
        if path == "/api/config":
            return {"environment": self.environment}
        if path == "/health":
            return {"status": "ok"}
        if path == "/users/db-has-users":
            return {"users_exist": self.users_exist}
        if path == "/users/create-first-user" and method == "POST":
            self.users_exist = True
            return {"id": "local-owner"}
        if path == "/sign-in" and method == "POST":
            if not self.allow_sign_in:
                raise provisioner.StudioHttpError(method=method, path=path, status=401)
            self.authenticated = True
            return None
        if path == "/auth-test":
            return {"user_email": provisioner.LOCAL_ADMIN_EMAIL}
        if path == "/api_keys" and method == "GET":
            return list(self.api_keys)
        if path == "/api_keys" and method == "POST":
            record = {
                "id": "api-key-id",
                "name": body["name"],
                "key": "jtel_local-api-key-secret",
            }
            self.api_keys.append(record)
            return record
        if path.startswith("/api/v1/evaluation-tokens?") and method == "GET":
            return {"items": list(self.access_tokens), "next_cursor": None}
        if path == "/api/v1/evaluation-tokens" and method == "POST":
            record = {
                "id": "access-token-id",
                "name": body["name"],
                "token": "jcli_local-access-token-secret",
                "scopes": body["scopes"],
                "expires_at": body["expires_at"],
            }
            self.access_tokens.append(record)
            return record
        raise AssertionError(f"unexpected request: {method} {path}")


def credentials() -> Any:
    return provisioner.ProvisionedCredentials(
        api_key="jtel_environment-file-secret",
        access_token="jcli_environment-file-secret",
        api_key_created=True,
        access_token_created=True,
    )


def create_example_templates(root: Path) -> dict[Path, bytes]:
    """Create minimal representative versions of every owned template."""

    contents = {
        Path("sdks/python/examples/ai_chat/.env.example"): (
            b"AI_CHAT_MODEL_PROVIDER=gemini\n"
            b"GEMINI_API_KEY=provider-secret\n"
            b"# JUNJO_AI_STUDIO_API_KEY=jtel_...\n"
            b"JUNJO_AI_STUDIO_OTLP_ENDPOINT=old:1\n"
            b"JUNJO_AI_STUDIO_OTLP_INSECURE=false\n"
            b"JUNJO_AI_STUDIO_BACKEND_BASE_URL=http://old:2\n"
            b"# JUNJO_AI_STUDIO_CLI_TOKEN=jcli_...\n"
            b"JUNJO_AI_STUDIO_FRONTEND_BASE_URL=http://old:3\n"
        ),
        Path("sdks/python/examples/base_openai_agents/.env.example"): (
            b"JUNJO_AI_STUDIO_API_KEY=\n"
            b"JUNJO_AI_STUDIO_OTLP_ENDPOINT=old:1\n"
            b"JUNJO_AI_STUDIO_OTLP_INSECURE=false\n"
            b"JUNJO_AI_STUDIO_BACKEND_BASE_URL=http://old:2\n"
            b"JUNJO_AI_STUDIO_CLI_TOKEN=\n"
            b"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=SPAN_ONLY\n"
        ),
        Path("sdks/python/examples/base/.env.example"): (
            b"JUNJO_AI_STUDIO_OTLP_ENDPOINT=old:1\n"
            b"JUNJO_AI_STUDIO_OTLP_INSECURE=false\n"
            b"# JUNJO_AI_STUDIO_API_KEY=jtel_...\n"
            b"# GEMINI_API_KEY=\n"
        ),
    }
    for relative_path, content in contents.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return contents


class LocalStudioProvisioningTests(unittest.TestCase):
    """Prove environment guards, API use, idempotence, and secret handling."""

    def test_backend_url_accepts_only_the_repository_local_boundary(self) -> None:
        self.assertEqual(
            provisioner.validate_backend_url("http://localhost:26154/"),
            "http://localhost:26154",
        )
        self.assertEqual(
            provisioner.validate_backend_url("http://127.0.0.1:26154"),
            "http://127.0.0.1:26154",
        )
        for value in (
            "https://localhost:26154",
            "http://studio.example.com:26154",
            "http://localhost:9999",
            "http://user:password@localhost:26154",
            "http://localhost:26154/api",
        ):
            with self.subTest(value=value), self.assertRaises(provisioner.ProvisioningError):
                provisioner.validate_backend_url(value)

    def test_runtime_guard_rejects_production_and_unknown_environments(self) -> None:
        for environment in ("production", "developement"):
            with self.subTest(environment=environment):
                client = FakeStudioClient(environment=environment)
                with self.assertRaisesRegex(
                    provisioner.ProvisioningError,
                    "requires Studio to report development mode",
                ):
                    provisioner.provision_studio(client)
                self.assertEqual(client.calls, [("/api/config", "GET", None)])

    def test_empty_studio_uses_first_user_api_and_exact_credential_contracts(self) -> None:
        client = FakeStudioClient(users_exist=False)
        result = provisioner.provision_studio(client)

        self.assertTrue(result.api_key_created)
        self.assertTrue(result.access_token_created)
        first_user_call = next(
            call for call in client.calls if call[0] == "/users/create-first-user"
        )
        self.assertEqual(
            first_user_call[2],
            {
                "email": provisioner.LOCAL_ADMIN_EMAIL,
                "password": provisioner.LOCAL_ADMIN_PASSWORD,
            },
        )
        api_key_call = next(
            call for call in client.calls if call[0] == "/api_keys" and call[1] == "POST"
        )
        self.assertEqual(api_key_call[2], {"name": provisioner.LOCAL_API_KEY_NAME})
        token_call = next(
            call
            for call in client.calls
            if call[0] == "/api/v1/evaluation-tokens" and call[1] == "POST"
        )
        self.assertEqual(
            token_call[2],
            {
                "name": provisioner.LOCAL_ACCESS_TOKEN_NAME,
                "scopes": list(provisioner.ACCESS_TOKEN_SCOPES),
                "expires_at": None,
            },
        )

    def test_existing_studio_signs_in_without_setup_or_password_mutation(self) -> None:
        client = FakeStudioClient(users_exist=True)
        provisioner.provision_studio(client)
        paths = [path for path, _, _ in client.calls]
        self.assertNotIn("/users/create-first-user", paths)
        self.assertFalse(any("password" in path and path != "/sign-in" for path in paths))

    def test_existing_studio_authentication_failure_stops_without_mutation(self) -> None:
        client = FakeStudioClient(users_exist=True, allow_sign_in=False)
        with self.assertRaisesRegex(provisioner.StudioHttpError, "POST /sign-in"):
            provisioner.provision_studio(client)
        self.assertEqual(
            [path for path, _, _ in client.calls],
            ["/api/config", "/health", "/users/db-has-users", "/sign-in"],
        )

    def test_second_provisioning_run_reuses_both_credentials(self) -> None:
        client = FakeStudioClient()
        first = provisioner.provision_studio(client)
        second = provisioner.provision_studio(client)

        self.assertTrue(first.api_key_created)
        self.assertTrue(first.access_token_created)
        self.assertFalse(second.api_key_created)
        self.assertFalse(second.access_token_created)
        self.assertEqual(len(client.api_keys), 1)
        self.assertEqual(len(client.access_tokens), 1)
        self.assertEqual(first.api_key, second.api_key)
        self.assertEqual(first.access_token, second.access_token)

    def test_duplicate_named_credentials_fail_instead_of_selecting_one(self) -> None:
        api_client = FakeStudioClient(users_exist=True)
        api_client.api_keys = [
            {"name": provisioner.LOCAL_API_KEY_NAME, "key": "first"},
            {"name": provisioner.LOCAL_API_KEY_NAME, "key": "second"},
        ]
        with self.assertRaisesRegex(provisioner.ProvisioningError, "Multiple API keys"):
            provisioner.provision_studio(api_client)

        token_client = FakeStudioClient(users_exist=True)
        token_client.api_keys = [{"name": provisioner.LOCAL_API_KEY_NAME, "key": "one"}]
        token_client.access_tokens = [
            {"name": provisioner.LOCAL_ACCESS_TOKEN_NAME, "token": "first"},
            {"name": provisioner.LOCAL_ACCESS_TOKEN_NAME, "token": "second"},
        ]
        with self.assertRaisesRegex(provisioner.ProvisioningError, "Multiple access tokens"):
            provisioner.provision_studio(token_client)

    def test_environment_render_updates_active_or_commented_assignments(self) -> None:
        rendered = provisioner.render_environment(
            "# comment\n# TOKEN=old\nOTHER=preserved\nACTIVE=old\n",
            {"TOKEN": "new", "ACTIVE": "newer", "MISSING": "added"},
        )
        self.assertEqual(
            rendered,
            "# comment\n"
            "TOKEN=new\n"
            "OTHER=preserved\n"
            "ACTIVE=newer\n"
            "\n"
            "# Added by tooling/scripts/provision_local_studio.py\n"
            "MISSING=added\n",
        )
        with self.assertRaisesRegex(
            provisioner.ProvisioningError,
            "multiple active TOKEN assignments",
        ):
            provisioner.render_environment(
                "TOKEN=one\nTOKEN=two\n",
                {"TOKEN": "new"},
            )

    def test_example_configuration_preserves_templates_and_provider_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            templates = create_example_templates(root)
            destinations = provisioner.configure_example_environments(
                root,
                credentials(),
                verify_ignored=False,
            )

            self.assertEqual(len(destinations), 3)
            for template, original in templates.items():
                self.assertEqual((root / template).read_bytes(), original)
                destination = (root / template).with_name(".env")
                self.assertTrue(destination.is_file())
                self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)

            ai_chat = (root / "sdks/python/examples/ai_chat/.env").read_text(encoding="utf-8")
            self.assertIn("GEMINI_API_KEY=provider-secret", ai_chat)
            self.assertIn(
                "JUNJO_AI_STUDIO_API_KEY=jtel_environment-file-secret",
                ai_chat,
            )
            self.assertIn(
                "JUNJO_AI_STUDIO_CLI_TOKEN=jcli_environment-file-secret",
                ai_chat,
            )
            self.assertEqual(ai_chat.count("JUNJO_AI_STUDIO_API_KEY="), 1)
            self.assertEqual(ai_chat.count("JUNJO_AI_STUDIO_CLI_TOKEN="), 1)

    def test_existing_environment_preserves_unrelated_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_example_templates(root)
            ai_chat = root / "sdks/python/examples/ai_chat/.env"
            ai_chat.write_text(
                "AI_CHAT_MODEL_PROVIDER=grok\n"
                "XAI_API_KEY=existing-provider-secret\n"
                "JUNJO_AI_STUDIO_API_KEY=old\n",
                encoding="utf-8",
            )
            provisioner.configure_example_environments(
                root,
                credentials(),
                verify_ignored=False,
            )
            updated = ai_chat.read_text(encoding="utf-8")
            self.assertIn("AI_CHAT_MODEL_PROVIDER=grok", updated)
            self.assertIn("XAI_API_KEY=existing-provider-secret", updated)
            self.assertNotIn("JUNJO_AI_STUDIO_API_KEY=old", updated)
            self.assertIn(
                "JUNJO_AI_STUDIO_API_KEY=jtel_environment-file-secret",
                updated,
            )

    def test_atomic_write_failure_preserves_existing_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_bytes(b"ORIGINAL=value\n")
            os.chmod(path, 0o644)
            with mock.patch.object(
                provisioner.os,
                "replace",
                side_effect=OSError("injected publication failure"),
            ):
                with self.assertRaisesRegex(OSError, "injected publication failure"):
                    provisioner.write_private_file_atomically(
                        path,
                        b"REPLACEMENT=value\n",
                    )
            self.assertEqual(path.read_bytes(), b"ORIGINAL=value\n")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual([item.name for item in path.parent.iterdir()], [".env"])

    def test_run_output_never_contains_canonical_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_example_templates(root)
            client = FakeStudioClient()
            output = io.StringIO()
            with (
                mock.patch.object(provisioner, "StudioClient", return_value=client),
                mock.patch.object(provisioner, "require_ignored_environment_files"),
                contextlib.redirect_stdout(output),
            ):
                result = provisioner.run(
                    backend_url=provisioner.DEFAULT_BACKEND_URL,
                    repository_root=root,
                )
            self.assertEqual(result, 0)
            rendered = output.getvalue()
            self.assertNotIn("jtel_local-api-key-secret", rendered)
            self.assertNotIn("jcli_local-access-token-secret", rendered)
            self.assertIn(provisioner.LOCAL_API_KEY_NAME, rendered)
            self.assertIn(provisioner.LOCAL_ACCESS_TOKEN_NAME, rendered)

    def test_real_example_environment_targets_are_gitignored(self) -> None:
        for target in provisioner.ENVIRONMENT_TARGETS:
            with self.subTest(path=target.relative_path):
                result = subprocess.run(
                    [
                        "git",
                        "check-ignore",
                        "--quiet",
                        "--",
                        str(target.relative_path),
                    ],
                    cwd=REPOSITORY_ROOT,
                    check=False,
                )
                self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
