#!/usr/bin/env python3
"""Validate fast platform-level monorepo invariants."""

from __future__ import annotations

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
    "contracts/telemetry/VERSION",
    "contracts/telemetry/README.md",
    "docs/adr/0001-junjo-platform-monorepo.md",
)


def require(condition: bool, message: str) -> None:
    """Raise a clear validation error when an invariant is false."""
    if not condition:
        raise RuntimeError(message)


def validate_layout() -> None:
    """Validate component roots, independent locks, licenses, and workflow ownership."""
    for relative_path in REQUIRED_PATHS:
        require((PLATFORM_ROOT / relative_path).is_file(), f"required file is missing: {relative_path}")

    nested_workflows = PLATFORM_ROOT / "apps" / "studio" / ".github" / "workflows"
    require(
        not nested_workflows.exists() or not any(nested_workflows.iterdir()),
        "active Studio workflows must live in the repository root .github/workflows",
    )


def validate_release_routing() -> None:
    """Keep product publishers isolated behind exact namespaced tag prefixes."""
    workflow_root = PLATFORM_ROOT / ".github" / "workflows"
    python_publish = (workflow_root / "python-publish.yml").read_text(encoding="utf-8")
    studio_publish = (workflow_root / "studio-docker-publish.yml").read_text(encoding="utf-8")

    require("startsWith(github.event.release.tag_name, 'sdk-python-v')" in python_publish,
            "Python publishing must be guarded by sdk-python-v tags")
    require("sdk-python-v${VERSION}" in python_publish,
            "Python publishing must validate the exact package version")
    require("startsWith(github.event.release.tag_name, 'studio-v')" in studio_publish,
            "Studio publishing must be guarded by studio-v tags")
    require("studio-v${VERSION}" in studio_publish,
            "Studio publishing must validate the exact Studio version")
    require("context: ./apps/studio" in studio_publish,
            "Studio images must build from the Studio project context")


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
    validate_release_routing()
    validate_contract()
    print("Junjo platform repository invariants are valid.")


if __name__ == "__main__":
    main()
