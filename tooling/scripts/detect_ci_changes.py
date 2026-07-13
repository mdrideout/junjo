#!/usr/bin/env python3
"""Map changed repository paths to the CI components that own them."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

COMPONENTS = (
    "python",
    "studio_backend",
    "studio_frontend",
    "studio_proto",
    "studio_rest",
    "studio_version",
    "telemetry",
    "deployments",
    "website",
)

RUN_ALL_PATHS = {
    ".github/dependabot.yml",
    "tooling/scripts/detect_ci_changes.py",
    "tooling/tests/test_ci_routing.py",
    "tooling/tests/test_ci_release_tools.py",
}
RUN_ALL_PREFIXES = (".github/actions/", ".github/workflows/")

STUDIO_CROSS_RUNTIME_PATHS = {
    "apps/studio/.dockerignore",
    "apps/studio/.env.example",
    "apps/studio/compose.yaml",
    "apps/studio/compose.monitoring.yaml",
    "apps/studio/scripts/junjo",
}

STUDIO_ALL_CHECK_PATHS = {
    "apps/studio/run-all-tests.sh",
    "apps/studio/scripts/install-git-hooks.sh",
    "apps/studio/scripts/pre-commit.sh",
}

STUDIO_ARTIFACT_LICENSE_PATHS = {
    "apps/studio/LICENSE",
    "apps/studio/THIRD_PARTY_NOTICES.md",
    "tooling/scripts/validate_studio_artifact_licenses.py",
    "tooling/tests/test_studio_artifact_licenses.py",
}

STUDIO_ARTIFACT_LICENSE_PREFIXES = ("apps/studio/licenses/",)

STUDIO_NON_PRODUCT_PATHS = {
    "apps/studio/.gitignore",
    "apps/studio/AGENTS.md",
    "apps/studio/PROTO_VERSIONS.md",
    "apps/studio/README.md",
    "apps/studio/TESTING.md",
    "apps/studio/junjo-screenshot.png",
}

STUDIO_NON_PRODUCT_PREFIXES = (
    "apps/studio/.agents/",
    "apps/studio/.claude/",
    "apps/studio/docs/",
)

STUDIO_PRODUCT_PREFIXES = (
    "apps/studio/backend/",
    "apps/studio/deployments/",
    "apps/studio/e2e_test_apps/",
    "apps/studio/frontend/",
    "apps/studio/ingestion/",
    "apps/studio/proto/",
    "apps/studio/scripts/",
    "apps/studio/test-fixtures/",
)


def _starts_with(path: str, *prefixes: str) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes)


def detect_components(paths: Iterable[str]) -> dict[str, bool]:
    """Return the component checks required by the changed paths."""
    normalized = {path.strip().removeprefix("./") for path in paths if path.strip()}
    result = {component: False for component in COMPONENTS}

    if normalized & RUN_ALL_PATHS or any(
        path.startswith(RUN_ALL_PREFIXES) for path in normalized
    ):
        return {component: True for component in COMPONENTS}

    unmapped_studio_paths = sorted(
        path
        for path in normalized
        if path.startswith("apps/studio/")
        and path not in STUDIO_NON_PRODUCT_PATHS
        and not path.startswith(STUDIO_NON_PRODUCT_PREFIXES)
        and path not in STUDIO_CROSS_RUNTIME_PATHS
        and path not in STUDIO_ALL_CHECK_PATHS
        and path not in STUDIO_ARTIFACT_LICENSE_PATHS
        and path != "apps/studio/VERSION"
        and path != "apps/studio/run-all-proto-gen.sh"
        and not path.startswith(STUDIO_ARTIFACT_LICENSE_PREFIXES)
        and not path.startswith(STUDIO_PRODUCT_PREFIXES)
    )
    if unmapped_studio_paths:
        raise RuntimeError(
            "Studio product path has no CI owner: " + ", ".join(unmapped_studio_paths)
        )

    for path in normalized:
        is_contract = path.startswith("contracts/telemetry/")
        is_artifact_license_input = (
            path in STUDIO_ARTIFACT_LICENSE_PATHS
            or path.startswith(STUDIO_ARTIFACT_LICENSE_PREFIXES)
        )

        if is_artifact_license_input:
            for component in (
                "studio_backend",
                "studio_frontend",
                "telemetry",
                "deployments",
            ):
                result[component] = True

        if path in STUDIO_ALL_CHECK_PATHS:
            for component in (
                "studio_backend",
                "studio_frontend",
                "studio_proto",
                "studio_rest",
                "studio_version",
                "telemetry",
                "deployments",
            ):
                result[component] = True

        if path in STUDIO_CROSS_RUNTIME_PATHS:
            result["studio_backend"] = True
            result["studio_frontend"] = True
            result["telemetry"] = True
            result["deployments"] = True

        if path == "apps/studio/run-all-proto-gen.sh":
            result["studio_backend"] = True
            result["studio_proto"] = True

        if path.startswith("apps/studio/e2e_test_apps/"):
            result["telemetry"] = True
            result["deployments"] = True

        if path.startswith("apps/studio/test-fixtures/"):
            result["studio_backend"] = True
            result["telemetry"] = True

        if (
            _starts_with(path, "sdks/python/")
            or is_contract
            or path == ".github/workflows/python-ci.yml"
        ):
            result["python"] = True

        if (
            _starts_with(
                path,
                "apps/studio/backend/",
                "apps/studio/ingestion/",
                "apps/studio/proto/",
            )
            or is_contract
            or path == ".github/workflows/studio-backend-tests.yml"
        ):
            result["studio_backend"] = True

        if (
            _starts_with(path, "apps/studio/frontend/")
            or is_contract
            or path == ".github/workflows/studio-frontend-tests.yml"
        ):
            result["studio_frontend"] = True

        if _starts_with(
            path, "apps/studio/proto/", "apps/studio/backend/app/proto_gen/"
        ) or path in {
            "apps/studio/backend/scripts/generate_proto.sh",
            "apps/studio/ingestion/build.rs",
            ".github/workflows/studio-proto-staleness-check.yml",
        }:
            result["studio_proto"] = True

        if (
            (
                path.startswith("apps/studio/backend/app/")
                and (path.endswith("schemas.py") or path.endswith("openapi.json"))
            )
            or _starts_with(path, "apps/studio/frontend/src/")
            and "schema" in path
        ):
            result["studio_rest"] = True
        if path in {
            "apps/studio/backend/scripts/export_openapi_schema.py",
            "apps/studio/backend/scripts/validate_rest_api_contracts.sh",
            ".github/workflows/studio-rest-api-contract-validation.yml",
        } or path.startswith("apps/studio/frontend/src/__tests__/contracts/"):
            result["studio_rest"] = True

        if path in {
            "apps/studio/VERSION",
            "apps/studio/backend/app/main.py",
            "apps/studio/backend/app/common/responses.py",
            "apps/studio/backend/pyproject.toml",
            "apps/studio/backend/uv.lock",
            "apps/studio/ingestion/Cargo.toml",
            "apps/studio/ingestion/Cargo.lock",
            "apps/studio/frontend/package.json",
            "apps/studio/frontend/package-lock.json",
            "apps/studio/frontend/backend/openapi.json",
            "apps/studio/scripts/check-version-sync.sh",
            "apps/studio/scripts/sync-version.sh",
            ".github/workflows/studio-version-sync-check.yml",
        }:
            result["studio_version"] = True

        if (
            is_contract
            or _starts_with(
                path,
                "sdks/python/src/junjo/telemetry/",
                "apps/studio/ingestion/",
                "apps/studio/backend/app/features/otel_spans/",
                "apps/studio/frontend/src/features/traces/",
            )
            or path
            in {
                "sdks/python/src/junjo/graph.py",
                "sdks/python/src/junjo/workflow.py",
                ".github/workflows/telemetry-contract.yml",
            }
        ):
            result["telemetry"] = True

        if (
            _starts_with(path, "apps/studio/deployments/")
            or path == "apps/studio/VERSION"
            or path
            in {
                "apps/studio/backend/Dockerfile",
                "apps/studio/frontend/Dockerfile",
                "apps/studio/ingestion/Dockerfile",
            }
            or _starts_with(
                path,
                "tooling/scripts/build_studio_release_evidence",
                "tooling/scripts/validate_studio_deployments",
                "tooling/scripts/export_studio_distribution",
                "tooling/scripts/publish_studio_distribution",
                "tooling/scripts/smoke_studio_distribution",
                "tooling/scripts/validate_studio_release_policy",
                "tooling/scripts/validate_studio_runtime",
            )
            or path
            in {
                "tooling/studio_release_contract.json",
                "tooling/tests/test_studio_deployment_tools.py",
                "tooling/tests/test_studio_release_evidence.py",
                "tooling/tests/test_studio_runtime.py",
                "tooling/tests/test_studio_setup_wizards.py",
            }
        ):
            result["deployments"] = True

        if (
            path.startswith("apps/website/")
            or path == ".github/workflows/website-ci.yml"
        ):
            result["website"] = True

    return result


def main() -> None:
    """Read changed paths and emit GitHub Actions boolean outputs."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "paths", nargs="*", help="Changed repository paths. Reads stdin when omitted."
    )
    parser.add_argument(
        "--all", action="store_true", help="Enable every component check."
    )
    parser.add_argument(
        "--github-output", type=Path, help="Append outputs to this GitHub output file."
    )
    args = parser.parse_args()

    paths = args.paths if args.paths else sys.stdin.read().splitlines()
    result = (
        {component: True for component in COMPONENTS}
        if args.all
        else detect_components(paths)
    )
    lines = [
        f"{component}={'true' if enabled else 'false'}"
        for component, enabled in result.items()
    ]

    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


if __name__ == "__main__":
    main()
