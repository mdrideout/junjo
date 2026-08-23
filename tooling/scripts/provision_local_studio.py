#!/usr/bin/env python3
"""Provision persistent credentials for the repository-local Studio stack.

This command deliberately uses Studio's public setup, session, and credential
management APIs. It never imports Studio runtime code, accesses SQLite, or
creates credentials during application startup.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_BACKEND_URL = "http://localhost:26154"
LOCAL_BACKEND_PORT = 26154
LOCAL_ADMIN_EMAIL = "admin@test.com"
LOCAL_ADMIN_PASSWORD = "JunjoAIStudioLocalTestPass1!"
LOCAL_API_KEY_NAME = "Local Development Application Telemetry"
LOCAL_ACCESS_TOKEN_NAME = "Local Development Developer Access"
ACCESS_TOKEN_SCOPES = (
    "evaluation:read",
    "evaluation:write",
    "evidence:read",
)
PRIVATE_FILE_MODE = 0o600


class ProvisioningError(RuntimeError):
    """One credential-free local provisioning failure."""


class StudioHttpError(ProvisioningError):
    """One safe Studio HTTP failure without request or response secrets."""

    def __init__(self, *, method: str, path: str, status: int) -> None:
        super().__init__(f"Studio returned HTTP {status}: {method} {path}")
        self.status = status


@dataclass(frozen=True, slots=True)
class ProvisionedCredentials:
    """Canonical local credentials and whether this invocation created them."""

    api_key: str
    access_token: str
    api_key_created: bool
    access_token_created: bool


@dataclass(frozen=True, slots=True)
class EnvironmentTarget:
    """One example environment file and the Studio variables it consumes."""

    relative_path: Path
    variable_names: tuple[str, ...]


ENVIRONMENT_TARGETS = (
    EnvironmentTarget(
        relative_path=Path("sdks/python/examples/ai_chat/.env"),
        variable_names=(
            "JUNJO_AI_STUDIO_API_KEY",
            "JUNJO_AI_STUDIO_OTLP_ENDPOINT",
            "JUNJO_AI_STUDIO_OTLP_INSECURE",
            "JUNJO_AI_STUDIO_BACKEND_BASE_URL",
            "JUNJO_AI_STUDIO_CLI_TOKEN",
            "JUNJO_AI_STUDIO_FRONTEND_BASE_URL",
        ),
    ),
    EnvironmentTarget(
        relative_path=Path("sdks/python/examples/base_openai_agents/.env"),
        variable_names=(
            "JUNJO_AI_STUDIO_API_KEY",
            "JUNJO_AI_STUDIO_OTLP_ENDPOINT",
            "JUNJO_AI_STUDIO_OTLP_INSECURE",
            "JUNJO_AI_STUDIO_BACKEND_BASE_URL",
            "JUNJO_AI_STUDIO_CLI_TOKEN",
        ),
    ),
    EnvironmentTarget(
        relative_path=Path("sdks/python/examples/base/.env"),
        variable_names=(
            "JUNJO_AI_STUDIO_API_KEY",
            "JUNJO_AI_STUDIO_OTLP_ENDPOINT",
            "JUNJO_AI_STUDIO_OTLP_INSECURE",
        ),
    ),
)


class StudioClient:
    """Small JSON client with an isolated Studio session-cookie jar."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: Mapping[str, object] | None = None,
    ) -> Any:
        """Issue one request without including request values in failures."""

        require(path.startswith("/"), "Studio API paths must begin with '/'")
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if encoded is not None else {}
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=encoded,
            method=method,
            headers=headers,
        )
        try:
            with self.opener.open(request) as response:
                payload = response.read()
        except urllib.error.HTTPError as error:
            error.read()
            raise StudioHttpError(
                method=method,
                path=path,
                status=error.code,
            ) from error
        except (urllib.error.URLError, OSError) as error:
            raise ProvisioningError(f"Studio API request failed: {method} {path}") from error

        if not payload:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError as error:
            raise ProvisioningError(f"Studio returned invalid JSON: {method} {path}") from error


def require(condition: bool, message: str) -> None:
    """Raise one explicit, credential-free provisioning error."""

    if not condition:
        raise ProvisioningError(message)


def require_object(value: object, description: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{description} must be a JSON object")
    return value


def require_list(value: object, description: str) -> list[Any]:
    require(isinstance(value, list), f"{description} must be a JSON array")
    return value


def require_secret(value: object, description: str) -> str:
    require(
        isinstance(value, str) and bool(value),
        f"{description} did not contain a credential",
    )
    return value


def validate_backend_url(value: str) -> str:
    """Accept only the repository-local HTTP backend boundary."""

    try:
        parsed = urllib.parse.urlparse(value)
        port = parsed.port
    except ValueError as error:
        raise ProvisioningError("Studio backend URL is invalid") from error

    require(parsed.scheme == "http", "Local provisioning requires an HTTP backend URL")
    require(
        parsed.hostname in {"localhost", "127.0.0.1", "::1"},
        "Local provisioning accepts only a loopback Studio backend",
    )
    require(
        port == LOCAL_BACKEND_PORT,
        f"Local provisioning requires Studio backend port {LOCAL_BACKEND_PORT}",
    )
    require(
        parsed.username is None and parsed.password is None,
        "Studio backend URL must not contain credentials",
    )
    require(
        parsed.path in {"", "/"} and not parsed.params and not parsed.query and not parsed.fragment,
        "Studio backend URL must not contain a path, query, or fragment",
    )
    return value.rstrip("/")


def validate_local_runtime(client: StudioClient) -> None:
    """Prove the target is a healthy Studio development runtime."""

    config = require_object(client.request("/api/config"), "Studio config response")
    require(
        config.get("environment") == "development",
        "Local provisioning requires Studio to report development mode",
    )
    health = require_object(client.request("/health"), "Studio health response")
    require(health.get("status") == "ok", "Studio backend is not healthy")


def authenticate_local_owner(client: StudioClient) -> None:
    """Create the local owner only on an empty Studio, then sign in normally."""

    status = require_object(
        client.request("/users/db-has-users"),
        "Studio setup-status response",
    )
    users_exist = status.get("users_exist")
    require(
        isinstance(users_exist, bool),
        "Studio setup-status response must contain users_exist",
    )
    if not users_exist:
        client.request(
            "/users/create-first-user",
            method="POST",
            body={
                "email": LOCAL_ADMIN_EMAIL,
                "password": LOCAL_ADMIN_PASSWORD,
            },
        )

    client.request(
        "/sign-in",
        method="POST",
        body={
            "email": LOCAL_ADMIN_EMAIL,
            "password": LOCAL_ADMIN_PASSWORD,
        },
    )
    authenticated = require_object(
        client.request("/auth-test"),
        "Studio authentication response",
    )
    require(
        authenticated.get("user_email") == LOCAL_ADMIN_EMAIL,
        "Studio did not authenticate the documented local owner",
    )


def find_or_create_api_key(client: StudioClient) -> tuple[str, bool]:
    """Return the one named persistent local telemetry credential."""

    records = require_list(client.request("/api_keys"), "API-key list response")
    matches = [
        require_object(record, "API-key record")
        for record in records
        if isinstance(record, dict) and record.get("name") == LOCAL_API_KEY_NAME
    ]
    require(
        len(matches) <= 1,
        f"Multiple API keys are named {LOCAL_API_KEY_NAME!r}; remove duplicates in Studio",
    )
    if matches:
        return require_secret(matches[0].get("key"), "Existing API-key record"), False

    created = require_object(
        client.request(
            "/api_keys",
            method="POST",
            body={"name": LOCAL_API_KEY_NAME},
        ),
        "API-key creation response",
    )
    require(
        created.get("name") == LOCAL_API_KEY_NAME,
        "Studio returned an unexpected API-key name",
    )
    return require_secret(created.get("key"), "API-key creation response"), True


def list_access_tokens(client: StudioClient) -> list[dict[str, Any]]:
    """Read every access-token page without assuming a record count."""

    records: list[dict[str, Any]] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    while True:
        query: dict[str, object] = {"limit": 100}
        if cursor is not None:
            query["cursor"] = cursor
        path = "/api/v1/evaluation-tokens?" + urllib.parse.urlencode(query)
        page = require_object(client.request(path), "Access-token list response")
        items = require_list(page.get("items"), "Access-token items")
        records.extend(require_object(item, "Access-token record") for item in items)

        next_cursor = page.get("next_cursor")
        require(
            next_cursor is None or isinstance(next_cursor, str),
            "Access-token next_cursor must be a string or null",
        )
        if next_cursor is None:
            return records
        require(next_cursor not in seen_cursors, "Access-token pagination repeated a cursor")
        seen_cursors.add(next_cursor)
        cursor = next_cursor


def find_or_create_access_token(client: StudioClient) -> tuple[str, bool]:
    """Return the one named persistent local developer credential."""

    matches = [
        record
        for record in list_access_tokens(client)
        if record.get("name") == LOCAL_ACCESS_TOKEN_NAME
    ]
    require(
        len(matches) <= 1,
        f"Multiple access tokens are named {LOCAL_ACCESS_TOKEN_NAME!r}; remove duplicates in Studio",
    )
    if matches:
        return require_secret(matches[0].get("token"), "Existing access-token record"), False

    created = require_object(
        client.request(
            "/api/v1/evaluation-tokens",
            method="POST",
            body={
                "name": LOCAL_ACCESS_TOKEN_NAME,
                "scopes": list(ACCESS_TOKEN_SCOPES),
                "expires_at": None,
            },
        ),
        "Access-token creation response",
    )
    require(
        created.get("name") == LOCAL_ACCESS_TOKEN_NAME,
        "Studio returned an unexpected access-token name",
    )
    return require_secret(created.get("token"), "Access-token creation response"), True


def provision_studio(client: StudioClient) -> ProvisionedCredentials:
    """Provision both persistent local credentials through normal APIs."""

    validate_local_runtime(client)
    authenticate_local_owner(client)
    api_key, api_key_created = find_or_create_api_key(client)
    access_token, access_token_created = find_or_create_access_token(client)
    return ProvisionedCredentials(
        api_key=api_key,
        access_token=access_token,
        api_key_created=api_key_created,
        access_token_created=access_token_created,
    )


def environment_values(credentials: ProvisionedCredentials) -> dict[str, str]:
    """Return the canonical repository-local example settings."""

    return {
        "JUNJO_AI_STUDIO_API_KEY": credentials.api_key,
        "JUNJO_AI_STUDIO_CLI_TOKEN": credentials.access_token,
        "JUNJO_AI_STUDIO_OTLP_ENDPOINT": "localhost:26155",
        "JUNJO_AI_STUDIO_OTLP_INSECURE": "true",
        "JUNJO_AI_STUDIO_BACKEND_BASE_URL": DEFAULT_BACKEND_URL,
        "JUNJO_AI_STUDIO_FRONTEND_BASE_URL": "http://localhost:26151",
    }


def render_environment(text: str, updates: Mapping[str, str]) -> str:
    """Update selected dotenv assignments while preserving unrelated content."""

    lines = text.splitlines()
    missing: list[tuple[str, str]] = []
    for key, value in updates.items():
        escaped = re.escape(key)
        active_pattern = re.compile(rf"^(\s*)(?:export\s+)?{escaped}\s*=.*$")
        commented_pattern = re.compile(rf"^(\s*)#\s*{escaped}\s*=.*$")
        active_indexes = [index for index, line in enumerate(lines) if active_pattern.match(line)]
        require(
            len(active_indexes) <= 1,
            f"Environment file contains multiple active {key} assignments",
        )
        if active_indexes:
            index = active_indexes[0]
            indentation = active_pattern.match(lines[index]).group(1)  # type: ignore[union-attr]
            lines[index] = f"{indentation}{key}={value}"
            continue

        commented_indexes = [
            index for index, line in enumerate(lines) if commented_pattern.match(line)
        ]
        if commented_indexes:
            index = commented_indexes[0]
            indentation = commented_pattern.match(lines[index]).group(1)  # type: ignore[union-attr]
            lines[index] = f"{indentation}{key}={value}"
            continue

        missing.append((key, value))

    if missing:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append("# Added by tooling/scripts/provision_local_studio.py")
        lines.extend(f"{key}={value}" for key, value in missing)
    return "\n".join(lines) + "\n"


def write_private_file_atomically(path: Path, contents: bytes) -> None:
    """Durably replace one ignored environment file with private permissions."""

    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=".junjo-example-env-staging-",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(file_descriptor, PRIVATE_FILE_MODE)
        temporary_file = os.fdopen(file_descriptor, "wb")
        file_descriptor = -1
        with temporary_file:
            temporary_file.write(contents)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, path)
        os.chmod(path, PRIVATE_FILE_MODE)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        temporary_path.unlink(missing_ok=True)
        raise


def require_ignored_environment_files(repository_root: Path) -> None:
    """Refuse to write secrets unless every target is ignored by Git."""

    for target in ENVIRONMENT_TARGETS:
        try:
            completed = subprocess.run(
                ["git", "check-ignore", "--quiet", "--", str(target.relative_path)],
                cwd=repository_root,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            raise ProvisioningError("Unable to verify ignored example environment files") from error
        require(
            completed.returncode == 0,
            f"Refusing to write an environment file that Git does not ignore: {target.relative_path}",
        )


def configure_example_environments(
    repository_root: Path,
    credentials: ProvisionedCredentials,
    *,
    verify_ignored: bool = True,
) -> tuple[Path, ...]:
    """Create or update supported example environments without touching templates."""

    if verify_ignored:
        require_ignored_environment_files(repository_root)
    values = environment_values(credentials)
    rendered: list[tuple[Path, bytes]] = []
    for target in ENVIRONMENT_TARGETS:
        destination = repository_root / target.relative_path
        template = destination.with_name(".env.example")
        require(template.is_file(), f"Example environment template is missing: {template}")
        source = destination if destination.exists() else template
        current = source.read_text(encoding="utf-8")
        updates = {name: values[name] for name in target.variable_names}
        contents = render_environment(current, updates).encode("utf-8")
        rendered.append((destination, contents))

    for destination, contents in rendered:
        write_private_file_atomically(destination, contents)
    return tuple(destination for destination, _ in rendered)


def run(*, backend_url: str, repository_root: Path) -> int:
    """Provision Studio and configure examples, printing no canonical secrets."""

    client = StudioClient(validate_backend_url(backend_url))
    credentials = provision_studio(client)
    configured_paths = configure_example_environments(repository_root, credentials)

    api_action = "created" if credentials.api_key_created else "reused"
    token_action = "created" if credentials.access_token_created else "reused"
    print("Local Studio development credentials are ready.")
    print(f"  Application Telemetry API Key: {LOCAL_API_KEY_NAME} ({api_action})")
    print(f"  Developer Access Token: {LOCAL_ACCESS_TOKEN_NAME} ({token_action})")
    print("Configured ignored example environments:")
    for path in configured_paths:
        print(f"  {path.relative_to(repository_root)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision credentials for the repository-local Studio development stack."
    )
    parser.add_argument(
        "--backend-url",
        default=DEFAULT_BACKEND_URL,
        help=f"Local Studio backend URL (default: {DEFAULT_BACKEND_URL})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository_root = Path(__file__).resolve().parents[2]
    try:
        return run(backend_url=args.backend_url, repository_root=repository_root)
    except (ProvisioningError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
