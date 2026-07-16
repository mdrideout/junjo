"""Black-box behavioral tests for every Studio setup wizard."""

from __future__ import annotations

import base64
import importlib.machinery
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Iterator
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SECRET_KEYS = (
    "JUNJO_SESSION_SECRET",
    "JUNJO_SECURE_COOKIE_KEY",
    "JUNJO_INTERNAL_GRPC_TOKEN",
)
PRODUCTION_HOSTNAME = "studio.example.test"
PRODUCTION_URLS = {
    "JUNJO_PROD_FRONTEND_URL": f"https://{PRODUCTION_HOSTNAME}",
    "JUNJO_PROD_BACKEND_URL": f"https://api.{PRODUCTION_HOSTNAME}",
    "JUNJO_PROD_INGESTION_URL": f"https://ingestion.{PRODUCTION_HOSTNAME}",
}


@dataclass(frozen=True)
class Wizard:
    """Describe one independently shipped Studio setup CLI."""

    name: str
    relative_root: Path

    def production_arguments(self, *, cloudflare_token: str) -> list[str]:
        if self.name == "root":
            return [
                "--env",
                "production",
                "--build-target",
                "production",
                "--prod-frontend-url",
                PRODUCTION_URLS["JUNJO_PROD_FRONTEND_URL"],
                "--prod-backend-url",
                PRODUCTION_URLS["JUNJO_PROD_BACKEND_URL"],
                "--prod-ingestion-url",
                PRODUCTION_URLS["JUNJO_PROD_INGESTION_URL"],
            ]
        arguments = [
            "--env",
            "production",
            "--hostname",
            PRODUCTION_HOSTNAME,
        ]
        if self.name == "vm-caddy":
            arguments.extend(["--cloudflare-token", cloudflare_token])
        return arguments


WIZARDS = (
    Wizard("root", Path("apps/studio")),
    Wizard("minimal", Path("apps/studio/deployments/minimal")),
    Wizard("vm-caddy", Path("apps/studio/deployments/vm-caddy")),
)


def parse_environment(path: Path) -> dict[str, str]:
    """Parse the simple KEY=value assignments written by the setup CLIs."""
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


def private_file_mode(path: Path) -> int:
    """Return only the permission bits for a private setup file."""
    return stat.S_IMODE(path.stat().st_mode)


def load_wizard_module(root: Path, wizard: Wizard) -> ModuleType:
    """Load an extensionless setup script without invoking its CLI entry point."""
    module_name = f"_junjo_setup_{wizard.name}_{id(root)}"
    loader = importlib.machinery.SourceFileLoader(
        module_name,
        str(root / "scripts/junjo"),
    )
    spec = importlib.util.spec_from_loader(module_name, loader)
    if spec is None:
        raise RuntimeError(f"Unable to load setup wizard: {wizard.name}")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class StudioSetupWizardTests(unittest.TestCase):
    """Execute the shipped CLIs in isolated filesystem copies."""

    @contextmanager
    def copied_wizard(self, wizard: Wizard) -> Iterator[Path]:
        with tempfile.TemporaryDirectory(
            prefix=f"junjo-{wizard.name}-setup-test-"
        ) as temporary_directory:
            source = REPOSITORY_ROOT / wizard.relative_root
            destination = Path(temporary_directory) / wizard.name
            (destination / "scripts").mkdir(parents=True)
            shutil.copy2(source / ".env.example", destination / ".env.example")
            shutil.copy2(source / "scripts/junjo", destination / "scripts/junjo")
            yield destination

    def run_setup(
        self,
        root: Path,
        *arguments: str,
        env_file: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(root / "scripts/junjo"),
                "setup",
                "--non-interactive",
                "--env-file",
                str(env_file or root / ".env"),
                *arguments,
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )

    def assert_success(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_generated_secrets(
        self,
        environment: dict[str, str],
        result: subprocess.CompletedProcess[str],
    ) -> None:
        output = result.stdout + result.stderr
        for key in SECRET_KEYS:
            secret = environment[key]
            self.assertEqual(len(base64.b64decode(secret, validate=True)), 32)
            self.assertNotIn(secret, output)
            self.assertNotIn(secret[:6], output)
            self.assertNotIn(secret[-4:], output)
        self.assertIn("<redacted>", output)

    def test_development_setup_writes_exact_profile_and_safe_secrets(self) -> None:
        for wizard in WIZARDS:
            with self.subTest(wizard=wizard.name), self.copied_wizard(wizard) as root:
                arguments = ["--env", "development", "--profile", "2g"]
                if wizard.name == "root":
                    arguments.extend(["--build-target", "development"])
                result = self.run_setup(root, *arguments)

                self.assert_success(result)
                environment = parse_environment(root / ".env")
                self.assertEqual(environment["JUNJO_ENV"], "development")
                self.assertEqual(environment["JUNJO_BACKEND_MEM_RESERVATION"], "700m")
                self.assertEqual(environment["JUNJO_BACKEND_MEM_LIMIT"], "1200m")
                self.assertEqual(environment["JUNJO_DF_TARGET_PARTITIONS"], "2")
                self.assertEqual(environment["JUNJO_DF_SPILL_POOL_MB"], "384")
                if wizard.name == "root":
                    self.assertEqual(environment["JUNJO_BUILD_TARGET"], "development")
                self.assert_generated_secrets(environment, result)
                self.assertEqual(private_file_mode(root / ".env"), 0o600)
                self.assertFalse((root / ".env.bak").exists())

    def test_production_setup_writes_exact_urls_without_logging_credentials(self) -> None:
        cloudflare_token = "setup-test-cloudflare-token-never-log"
        for wizard in WIZARDS:
            with self.subTest(wizard=wizard.name), self.copied_wizard(wizard) as root:
                result = self.run_setup(
                    root,
                    *wizard.production_arguments(cloudflare_token=cloudflare_token),
                    "--profile",
                    "4g",
                )

                self.assert_success(result)
                environment = parse_environment(root / ".env")
                self.assertEqual(environment["JUNJO_ENV"], "production")
                self.assertEqual(environment["JUNJO_BACKEND_MEM_RESERVATION"], "1200m")
                self.assertEqual(environment["JUNJO_BACKEND_MEM_LIMIT"], "2500m")
                self.assertEqual(environment["JUNJO_DF_TARGET_PARTITIONS"], "4")
                for key, expected in PRODUCTION_URLS.items():
                    self.assertEqual(environment[key], expected)
                self.assert_generated_secrets(environment, result)
                self.assertEqual(private_file_mode(root / ".env"), 0o600)
                output = result.stdout + result.stderr
                self.assertNotIn(cloudflare_token, output)
                if wizard.name == "vm-caddy":
                    self.assertEqual(
                        environment["CLOUDFLARE_API_TOKEN"], cloudflare_token
                    )

    def test_missing_production_inputs_fail_without_writing_environment(self) -> None:
        for wizard in WIZARDS:
            with self.subTest(wizard=wizard.name), self.copied_wizard(wizard) as root:
                result = self.run_setup(root, "--env", "production")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((root / ".env").exists())
                self.assertFalse((root / ".env.bak").exists())

    def test_invalid_production_inputs_fail_without_writing_environment(self) -> None:
        for wizard in WIZARDS:
            with self.subTest(wizard=wizard.name), self.copied_wizard(wizard) as root:
                if wizard.name == "root":
                    arguments = [
                        "--env",
                        "production",
                        "--prod-frontend-url",
                        "not-a-url",
                        "--prod-backend-url",
                        PRODUCTION_URLS["JUNJO_PROD_BACKEND_URL"],
                        "--prod-ingestion-url",
                        PRODUCTION_URLS["JUNJO_PROD_INGESTION_URL"],
                    ]
                else:
                    arguments = ["--env", "production", "--hostname", "localhost"]
                    if wizard.name == "vm-caddy":
                        arguments.extend(
                            ["--cloudflare-token", "invalid-host-test-token"]
                        )
                result = self.run_setup(root, *arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((root / ".env").exists())

                sentinel = b"JUNJO_ENV=development\nSENTINEL=unchanged\n"
                (root / ".env").write_bytes(sentinel)
                os.chmod(root / ".env", 0o644)
                result = self.run_setup(root, *arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((root / ".env").read_bytes(), sentinel)
                self.assertEqual(private_file_mode(root / ".env"), 0o644)
                self.assertFalse((root / ".env.bak").exists())

    def test_vm_production_requires_cloudflare_token(self) -> None:
        wizard = next(item for item in WIZARDS if item.name == "vm-caddy")
        with self.copied_wizard(wizard) as root:
            result = self.run_setup(
                root,
                "--env",
                "production",
                "--hostname",
                PRODUCTION_HOSTNAME,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--cloudflare-token is required", result.stdout)
            self.assertFalse((root / ".env").exists())

    def test_dry_run_never_writes_or_changes_files(self) -> None:
        for wizard in WIZARDS:
            with self.subTest(wizard=wizard.name), self.copied_wizard(wizard) as root:
                result = self.run_setup(
                    root,
                    "--dry-run",
                    "--env",
                    "development",
                    "--profile",
                    "4g",
                )
                self.assert_success(result)
                self.assertFalse((root / ".env").exists())
                self.assertFalse((root / ".env.bak").exists())

                sentinel = b"JUNJO_ENV=development\nSENTINEL=unchanged\n"
                (root / ".env").write_bytes(sentinel)
                os.chmod(root / ".env", 0o644)
                result = self.run_setup(
                    root,
                    "--dry-run",
                    "--force-secrets",
                    "--env",
                    "development",
                    "--profile",
                    "4g",
                )
                self.assert_success(result)
                self.assertEqual((root / ".env").read_bytes(), sentinel)
                self.assertEqual(private_file_mode(root / ".env"), 0o644)
                self.assertFalse((root / ".env.bak").exists())

    def test_rerun_preserves_secrets_and_backs_up_exact_prior_file(self) -> None:
        for wizard in WIZARDS:
            with self.subTest(wizard=wizard.name), self.copied_wizard(wizard) as root:
                first = self.run_setup(
                    root, "--env", "development", "--profile", "1g"
                )
                self.assert_success(first)
                before = (root / ".env").read_bytes()
                os.chmod(root / ".env", 0o644)
                secrets_before = {
                    key: parse_environment(root / ".env")[key] for key in SECRET_KEYS
                }

                second = self.run_setup(
                    root, "--env", "development", "--profile", "4g"
                )
                self.assert_success(second)
                self.assertEqual((root / ".env.bak").read_bytes(), before)
                self.assertEqual(private_file_mode(root / ".env.bak"), 0o600)
                self.assertEqual(private_file_mode(root / ".env"), 0o600)
                after = parse_environment(root / ".env")
                self.assertEqual(
                    {key: after[key] for key in SECRET_KEYS}, secrets_before
                )

    def test_force_secrets_rotates_all_secrets_without_logging_them(self) -> None:
        for wizard in WIZARDS:
            with self.subTest(wizard=wizard.name), self.copied_wizard(wizard) as root:
                first = self.run_setup(root, "--env", "development")
                self.assert_success(first)
                before = parse_environment(root / ".env")

                second = self.run_setup(
                    root, "--env", "development", "--force-secrets"
                )
                self.assert_success(second)
                after = parse_environment(root / ".env")
                for key in SECRET_KEYS:
                    self.assertNotEqual(before[key], after[key])
                self.assert_generated_secrets(after, second)

    def test_atomic_writer_uses_same_directory_private_staging_file(self) -> None:
        for wizard in WIZARDS:
            with self.subTest(wizard=wizard.name), self.copied_wizard(wizard) as root:
                module = load_wizard_module(root, wizard)
                destination = root / ".env"
                observed: dict[str, object] = {}
                replace = os.replace

                def inspect_then_replace(source: str, target: str) -> None:
                    source_path = Path(source)
                    observed["parent"] = source_path.parent
                    observed["name"] = source_path.name
                    observed["mode"] = private_file_mode(source_path)
                    observed["target"] = Path(target)
                    replace(source, target)

                with mock.patch.object(
                    module.os,
                    "replace",
                    side_effect=inspect_then_replace,
                ):
                    module.write_private_file_atomically(
                        destination,
                        b"PRIVATE=contents\n",
                    )

                self.assertEqual(observed["parent"], destination.parent)
                self.assertTrue(
                    str(observed["name"]).startswith(".junjo-env-staging-")
                )
                self.assertEqual(observed["mode"], 0o600)
                self.assertEqual(observed["target"], destination)
                self.assertEqual(destination.read_bytes(), b"PRIVATE=contents\n")
                self.assertEqual(private_file_mode(destination), 0o600)

    def test_atomic_writer_failure_preserves_destination_and_removes_staging(self) -> None:
        for wizard in WIZARDS:
            with self.subTest(wizard=wizard.name), self.copied_wizard(wizard) as root:
                module = load_wizard_module(root, wizard)
                destination = root / ".env"
                original = b"PRIVATE=original\n"
                destination.write_bytes(original)
                os.chmod(destination, 0o644)
                entries_before = {path.name for path in root.iterdir()}

                with mock.patch.object(
                    module.os,
                    "replace",
                    side_effect=OSError("injected publication failure"),
                ):
                    with self.assertRaisesRegex(
                        OSError,
                        "injected publication failure",
                    ):
                        module.write_private_file_atomically(
                            destination,
                            b"PRIVATE=replacement\n",
                        )

                self.assertEqual(destination.read_bytes(), original)
                self.assertEqual(private_file_mode(destination), 0o644)
                self.assertEqual(
                    {path.name for path in root.iterdir()},
                    entries_before,
                )

    def test_publication_failure_is_safe_and_does_not_log_generated_secrets(self) -> None:
        for wizard in WIZARDS:
            with self.subTest(wizard=wizard.name), self.copied_wizard(wizard) as root:
                destination = root / "missing-parent" / ".env"
                result = self.run_setup(
                    root,
                    "--env",
                    "development",
                    env_file=destination,
                )

                self.assertNotEqual(result.returncode, 0)
                output = result.stdout + result.stderr
                self.assertIn(
                    "Error: unable to write private environment files:",
                    output,
                )
                self.assertNotIn("Traceback", output)
                self.assertNotRegex(output, r"[A-Za-z0-9+/]{43}=")
                self.assertFalse(destination.exists())
                self.assertFalse(destination.with_name(".env.bak").exists())
                self.assertFalse(destination.parent.exists())

    def test_secret_environment_and_backup_paths_are_ignored(self) -> None:
        paths: list[str] = []
        for wizard in WIZARDS:
            paths.extend(
                [
                    str(wizard.relative_root / ".env"),
                    str(wizard.relative_root / ".env.bak"),
                    str(wizard.relative_root / ".junjo-env-staging-interrupted"),
                ]
            )
        for path in paths:
            with self.subTest(path=path):
                result = subprocess.run(
                    ["git", "check-ignore", "--quiet", "--", path],
                    cwd=REPOSITORY_ROOT,
                    check=False,
                )
                self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
