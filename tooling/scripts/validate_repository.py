#!/usr/bin/env python3
"""Validate fast platform-level monorepo invariants."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

PLATFORM_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_PATHS = (
    "AGENTS.md",
    "LICENSE",
    "sdks/python/AGENTS.md",
    "sdks/python/LICENSE",
    "sdks/python/pyproject.toml",
    "sdks/python/uv.lock",
    "apps/studio/AGENTS.md",
    "apps/studio/LICENSE",
    "apps/studio/VERSION",
    "apps/studio/backend/uv.lock",
    "apps/studio/frontend/package-lock.json",
    "apps/studio/ingestion/Cargo.lock",
    "apps/studio/deployments/minimal/.gitignore",
    "apps/studio/deployments/minimal/LICENSE",
    "apps/studio/deployments/minimal/docker-compose.yml",
    "apps/studio/deployments/vm-caddy/.gitignore",
    "apps/studio/deployments/vm-caddy/LICENSE",
    "apps/studio/deployments/vm-caddy/docker-compose.yml",
    "apps/website/AGENTS.md",
    "apps/website/LICENSE",
    "apps/website/package-lock.json",
    "contracts/telemetry/VERSION",
    "contracts/telemetry/README.md",
    "docs/adr/0001-junjo-platform-monorepo.md",
    "docs/roadmaps/MONOREPO_GITHUB_CUTOVER_RUNBOOK.md",
    ".github/dependabot.yml",
    ".github/workflows/platform-gate.yml",
    ".github/workflows/studio-deployments.yml",
    ".github/workflows/website-ci.yml",
    "tooling/scripts/detect_ci_changes.py",
    "tooling/scripts/build_studio_release_evidence.py",
    "tooling/scripts/export_studio_distribution.py",
    "tooling/scripts/publish_studio_distribution.py",
    "tooling/scripts/validate_studio_deployments.py",
    "tooling/tests/test_ci_release_tools.py",
    "tooling/tests/test_studio_deployment_tools.py",
    "tooling/tests/test_studio_release_evidence.py",
)

LICENSE_PATHS = (
    "sdks/python/LICENSE",
    "apps/studio/LICENSE",
    "apps/studio/deployments/minimal/LICENSE",
    "apps/studio/deployments/vm-caddy/LICENSE",
    "apps/website/LICENSE",
)

LOCAL_SECRET_STATE = (
    "apps/studio/.env.bak",
    "apps/studio/deployments/minimal/.env.bak",
    "apps/studio/deployments/vm-caddy/.env.bak",
)


def require(condition: bool, message: str) -> None:
    """Raise a clear validation error when an invariant is false."""
    if not condition:
        raise RuntimeError(message)


def validate_layout() -> None:
    """Validate component roots, independent locks, licenses, and workflow ownership."""
    for relative_path in REQUIRED_PATHS:
        require(
            (PLATFORM_ROOT / relative_path).is_file(),
            f"required file is missing: {relative_path}",
        )

    nested_workflows = PLATFORM_ROOT / "apps" / "studio" / ".github" / "workflows"
    require(
        not nested_workflows.exists() or not any(nested_workflows.iterdir()),
        "active Studio workflows must live in the repository root .github/workflows",
    )


def validate_licensing() -> None:
    """Require every Junjo-authored component to carry the root Apache-2.0 license."""
    root_license = (PLATFORM_ROOT / "LICENSE").read_bytes()
    require(
        b"Apache License\n                           Version 2.0" in root_license,
        "root LICENSE must contain the Apache License 2.0 text",
    )
    for relative_path in LICENSE_PATHS:
        require(
            (PLATFORM_ROOT / relative_path).read_bytes() == root_license,
            f"component license must exactly match root LICENSE: {relative_path}",
        )


def validate_secret_boundaries() -> None:
    """Keep setup backups ignored and absent from the canonical source tree."""
    for relative_path in LOCAL_SECRET_STATE:
        ignore_result = subprocess.run(
            ["git", "check-ignore", "--quiet", relative_path],
            cwd=PLATFORM_ROOT,
            check=False,
        )
        require(
            ignore_result.returncode == 0,
            f"secret-bearing setup backup must be ignored: {relative_path}",
        )

    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=PLATFORM_ROOT,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    tracked_paths = {path.decode("utf-8") for path in tracked if path}
    for relative_path in LOCAL_SECRET_STATE:
        require(
            relative_path not in tracked_paths,
            f"secret-bearing setup backup must not be tracked: {relative_path}",
        )

    for distribution in ("minimal", "vm-caddy"):
        relative_path = f"apps/studio/deployments/{distribution}/.gitignore"
        ignore_rules = (
            (PLATFORM_ROOT / relative_path).read_text(encoding="utf-8").splitlines()
        )
        require(
            ".env.bak" in ignore_rules,
            f"standalone distribution must explicitly ignore .env.bak: {relative_path}",
        )


def validate_release_routing() -> None:
    """Keep product publishers isolated behind exact namespaced tag prefixes."""
    workflow_root = PLATFORM_ROOT / ".github" / "workflows"
    python_publish = (workflow_root / "python-publish.yml").read_text(encoding="utf-8")
    studio_publish = (workflow_root / "studio-docker-publish.yml").read_text(
        encoding="utf-8"
    )
    platform_gate = (workflow_root / "platform-gate.yml").read_text(encoding="utf-8")

    require(
        "startsWith(github.event.release.tag_name, 'sdk-python-v')" in python_publish,
        "Python publishing must be guarded by sdk-python-v tags",
    )
    require(
        "sdk-python-v${VERSION}" in python_publish,
        "Python publishing must validate the exact package version",
    )
    require(
        '- "studio-v*"' in studio_publish,
        "Studio publishing must be triggered only by studio-v tags",
    )
    require(
        "studio-v${VERSION}" in studio_publish,
        "Studio publishing must validate the exact Studio version",
    )
    require(
        "context: ./apps/studio" in studio_publish,
        "Studio images must build from the Studio project context",
    )
    require(
        "environment: studio-dockerhub-production" in studio_publish,
        "Studio image mutation must use its protected production environment",
    )
    require(
        "environment: studio-distributions-production" in studio_publish,
        "Studio mirror mutation must use its protected production environment",
    )
    require(
        "needs: [prepare, deployments, smoke_exact_release]" in studio_publish,
        "distribution publication must wait for deployment and exact-image smoke checks",
    )
    require(
        "needs: [prepare, publish_distributions]" in studio_publish,
        "floating image tags must wait for successful distribution publication",
    )
    require(
        "Publish GitHub release last" in studio_publish,
        "the GitHub release must be the final publication step",
    )
    require(
        "python3 tooling/scripts/build_studio_release_evidence.py" in studio_publish,
        "Studio publishing must validate complete release evidence before release creation",
    )
    require(
        "name: required" in platform_gate and "if: always()" in platform_gate,
        "the platform gate must expose one stable final required check",
    )


def validate_workflow_action_pins() -> None:
    """Require immutable commits for every external GitHub Action dependency."""
    workflow_root = PLATFORM_ROOT / ".github" / "workflows"
    for workflow in sorted(workflow_root.glob("*.yml")):
        for line_number, line in enumerate(
            workflow.read_text(encoding="utf-8").splitlines(), start=1
        ):
            match = re.search(r"\buses:\s+([^\s#]+)", line)
            if match is None:
                continue
            action = match.group(1)
            if action.startswith("./"):
                continue
            require(
                re.search(r"@[0-9a-f]{40}$", action) is not None,
                f"external action must use an immutable commit: "
                f"{workflow.relative_to(PLATFORM_ROOT)}:{line_number}: {action}",
            )


def validate_contract() -> None:
    """Run the dependency-free canonical telemetry contract validation."""
    subprocess.run(
        ["python3", "contracts/telemetry/compatibility/validate_contract.py"],
        cwd=PLATFORM_ROOT,
        check=True,
    )


def main() -> None:
    """Validate all fast repository-level invariants."""
    validate_layout()
    validate_licensing()
    validate_secret_boundaries()
    validate_release_routing()
    validate_workflow_action_pins()
    validate_contract()
    print("Junjo platform repository invariants are valid.")


if __name__ == "__main__":
    main()
