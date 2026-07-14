#!/usr/bin/env python3
"""Validate fast platform-level monorepo invariants."""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from pathlib import Path

from validate_studio_artifact_licenses import (
    check_inventories,
    load_policy as load_artifact_license_policy,
    validate_image_and_notice_contracts,
)
from validate_studio_release_policy import load_release_contract, parse_version

PLATFORM_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_PATHS = (
    "AGENTS.md",
    "LICENSE",
    "sdks/python/AGENTS.md",
    "sdks/python/LICENSE",
    "sdks/python/.python-version",
    "sdks/python/pyproject.toml",
    "sdks/python/RELEASE_POLICY.md",
    "sdks/python/uv.lock",
    "apps/studio/AGENTS.md",
    "apps/studio/LICENSE",
    "apps/studio/THIRD_PARTY_NOTICES.md",
    "apps/studio/licenses/artifact-license-policy.json",
    "apps/studio/licenses/frontend-production.json",
    "apps/studio/licenses/ingestion-production.json",
    "apps/studio/VERSION",
    "apps/studio/backend/uv.lock",
    "apps/studio/frontend/package-lock.json",
    "apps/studio/ingestion/Cargo.lock",
    "apps/studio/docs/adr/004-events-json-contract.md",
    "apps/studio/docs/adr/005-studio-frontend-interaction-foundation.md",
    "apps/studio/docs/adr/006-studio-release-transaction.md",
    "apps/studio/docs/adr/007-agent-execution-diagnostics.md",
    "apps/studio/deployments/minimal/.gitignore",
    "apps/studio/deployments/minimal/LICENSE",
    "apps/studio/deployments/minimal/docker-compose.yml",
    "apps/studio/deployments/vm-caddy/.gitignore",
    "apps/studio/deployments/vm-caddy/LICENSE",
    "apps/studio/deployments/vm-caddy/docker-compose.yml",
    "apps/website/AGENTS.md",
    "apps/website/LICENSE",
    "apps/website/package-lock.json",
    "apps/website/scripts/validate-build.mjs",
    "contracts/telemetry/VERSION",
    "contracts/telemetry/README.md",
    "docs/adr/0001-junjo-platform-monorepo.md",
    "docs/adr/0002-platform-licensing-and-third-party-material.md",
    "docs/adr/0003-agent-execution-model.md",
    "docs/adr/0004-agent-model-driver-and-tool-contracts.md",
    "docs/adr/0005-agent-workflow-composition.md",
    "docs/adr/0006-agent-telemetry-contract.md",
    "docs/adr/0007-execution-correlation-and-studio-resolution.md",
    "docs/adr/0008-versioned-application-object-persistence.md",
    "docs/roadmaps/AGENT_LAYER_PHASE_0.md",
    "docs/roadmaps/AGENT_LAYER_ROADMAP.md",
    "docs/roadmaps/AI_CHAT_TURN_PERSISTENCE_AND_DIAGNOSTICS.md",
    "docs/roadmaps/MONOREPO_MIGRATION_RECORD.md",
    ".github/dependabot.yml",
    ".github/workflows/platform-gate.yml",
    ".github/workflows/python-ci.yml",
    ".github/workflows/python-examples-smoke.yml",
    ".github/workflows/python-publish.yml",
    ".github/workflows/studio-deployments.yml",
    ".github/workflows/studio-docker-publish.yml",
    ".github/workflows/studio-release-validation.yml",
    ".github/workflows/website-ci.yml",
    "tooling/scripts/build_studio_release_evidence.py",
    "tooling/scripts/export_studio_distribution.py",
    "tooling/scripts/publish_studio_distribution.py",
    "tooling/scripts/smoke_studio_distribution.py",
    "tooling/scripts/validate_agent_studio_e2e.py",
    "apps/studio/frontend/e2e/live-agent.mjs",
    "tooling/scripts/validate_studio_deployments.py",
    "tooling/scripts/validate_studio_artifact_licenses.py",
    "tooling/scripts/validate_studio_release_policy.py",
    "tooling/scripts/validate_studio_runtime.py",
    "tooling/studio_release_contract.json",
    "tooling/tests/test_agent_studio_e2e.py",
    "tooling/tests/test_ci_release_tools.py",
    "tooling/tests/test_studio_artifact_licenses.py",
    "tooling/tests/test_studio_deployment_tools.py",
    "tooling/tests/test_studio_release_evidence.py",
    "tooling/tests/test_studio_runtime.py",
    "tooling/tests/test_studio_setup_wizards.py",
)

LICENSE_PATHS = (
    "sdks/python/LICENSE",
    "apps/studio/LICENSE",
    "apps/studio/deployments/minimal/LICENSE",
    "apps/studio/deployments/vm-caddy/LICENSE",
    "apps/website/LICENSE",
)

LOCAL_SECRET_STATE = (
    "apps/studio/.env",
    "apps/studio/.env.bak",
    "apps/studio/.junjo-env-staging-interrupted",
    "apps/studio/deployments/minimal/.env",
    "apps/studio/deployments/minimal/.env.bak",
    "apps/studio/deployments/minimal/.junjo-env-staging-interrupted",
    "apps/studio/deployments/vm-caddy/.env",
    "apps/studio/deployments/vm-caddy/.env.bak",
    "apps/studio/deployments/vm-caddy/.junjo-env-staging-interrupted",
)

LICENSE_METADATA = (
    ("sdks/python/pyproject.toml", "toml", "project"),
    ("apps/studio/backend/pyproject.toml", "toml", "project"),
    ("apps/studio/e2e_test_apps/app/pyproject.toml", "toml", "project"),
    (
        "apps/studio/e2e_test_apps/orchestration/pyproject.toml",
        "toml",
        "project",
    ),
    ("apps/studio/ingestion/Cargo.toml", "toml", "package"),
    ("apps/studio/frontend/package.json", "json", ""),
    ("apps/website/package.json", "json", ""),
)

JUNJO_DOCKERFILES = (
    "apps/studio/backend/Dockerfile",
    "apps/studio/frontend/Dockerfile",
    "apps/studio/ingestion/Dockerfile",
    "apps/studio/deployments/vm-caddy/caddy/Dockerfile",
    "apps/studio/deployments/vm-caddy/junjo_app/Dockerfile",
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
    """Require Apache metadata and notices on every Junjo-authored artifact."""
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

    for relative_path, file_type, section in LICENSE_METADATA:
        path = PLATFORM_ROOT / relative_path
        if file_type == "toml":
            value = tomllib.loads(path.read_text(encoding="utf-8"))
            metadata = value.get(section)
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
            metadata = value
        require(
            isinstance(metadata, dict) and metadata.get("license") == "Apache-2.0",
            f"package metadata must declare Apache-2.0: {relative_path}",
        )

    source_label = (
        'org.opencontainers.image.source="https://github.com/mdrideout/junjo"'
    )
    license_label = 'org.opencontainers.image.licenses="Apache-2.0"'
    for relative_path in JUNJO_DOCKERFILES:
        dockerfile = (PLATFORM_ROOT / relative_path).read_text(encoding="utf-8")
        require(
            source_label in dockerfile,
            f"container must declare its canonical OCI source: {relative_path}",
        )
        require(
            license_label in dockerfile,
            f"container must declare its Apache-2.0 OCI license: {relative_path}",
        )

    notice = (PLATFORM_ROOT / "apps/studio/THIRD_PARTY_NOTICES.md").read_text(
        encoding="utf-8"
    )
    require(
        "Base UI" in notice and "MIT" in notice,
        "Studio THIRD_PARTY_NOTICES.md must preserve the Base UI MIT notice",
    )

    artifact_policy = load_artifact_license_policy()
    check_inventories(artifact_policy, with_cargo_metadata=False)
    validate_image_and_notice_contracts(artifact_policy)


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
            f"secret-bearing setup state must be ignored: {relative_path}",
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
            f"secret-bearing setup state must not be tracked: {relative_path}",
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
        require(
            ".junjo-env-staging-*" in ignore_rules,
            "standalone distribution must explicitly ignore setup staging files: "
            f"{relative_path}",
        )

    gitleaks_path = PLATFORM_ROOT / ".gitleaks.toml"
    gitleaks = tomllib.loads(gitleaks_path.read_text(encoding="utf-8"))

    def reject_path_or_regex_allowlists(
        value: object, *, in_allowlist: bool = False
    ) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_is_allowlist = in_allowlist or "allowlist" in key.lower()
                require(
                    not (
                        child_is_allowlist
                        and key.lower() in {"paths", "regexes"}
                        and bool(child)
                    ),
                    ".gitleaks.toml must not contain path or regex allowlists",
                )
                reject_path_or_regex_allowlists(child, in_allowlist=child_is_allowlist)
        elif isinstance(value, list):
            for child in value:
                reject_path_or_regex_allowlists(child, in_allowlist=in_allowlist)

    reject_path_or_regex_allowlists(gitleaks)


def validate_studio_frontend_foundation() -> None:
    """Keep Catalyst out and Base UI behind Junjo-owned component boundaries."""
    frontend_root = PLATFORM_ROOT / "apps/studio/frontend"
    catalyst_root = frontend_root / "src/components/catalyst"
    require(
        not catalyst_root.exists(),
        "the Tailwind Plus Catalyst component tree must be absent from HEAD",
    )

    package = json.loads((frontend_root / "package.json").read_text(encoding="utf-8"))
    dependencies = package.get("dependencies")
    development_dependencies = package.get("devDependencies")
    require(isinstance(dependencies, dict), "frontend dependencies must be an object")
    require(
        isinstance(development_dependencies, dict),
        "frontend devDependencies must be an object",
    )
    require(
        isinstance(dependencies.get("@base-ui/react"), str)
        and bool(dependencies["@base-ui/react"]),
        "Studio must declare the standalone @base-ui/react foundation",
    )
    forbidden_dependencies = {
        "@headlessui/react",
        "framer-motion",
        "@radix-ui/react-switch",
        "radix-ui",
    }
    declared_dependencies = set(dependencies) | set(development_dependencies)
    require(
        not (declared_dependencies & forbidden_dependencies),
        "obsolete UI primitive dependencies must be removed: "
        f"{sorted(declared_dependencies & forbidden_dependencies)}",
    )

    allowed_base_ui_roots = (
        "components/actions/",
        "components/forms/",
        "components/layout/",
        "components/navigation/",
        "components/overlays/",
    )
    base_ui_importers: list[str] = []
    catalyst_references: list[str] = []
    source_root = frontend_root / "src"
    for path in sorted((*source_root.rglob("*.ts"), *source_root.rglob("*.tsx"))):
        source = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(source_root).as_posix()
        if "@base-ui/react" in source:
            base_ui_importers.append(relative_path)
            require(
                relative_path.startswith(allowed_base_ui_roots),
                "feature code must consume Junjo UI contracts instead of Base UI "
                f"directly: {relative_path}",
            )
        if "components/catalyst" in source or "/catalyst/" in source:
            catalyst_references.append(relative_path)
    require(bool(base_ui_importers), "the Junjo shared UI layer must use Base UI")
    require(
        not catalyst_references,
        f"current frontend source still references Catalyst: {catalyst_references}",
    )

    dockerfile = (frontend_root / "Dockerfile").read_text(encoding="utf-8")
    require(
        "COPY LICENSE THIRD_PARTY_NOTICES.md /usr/share/licenses/junjo-ai-studio/"
        in dockerfile,
        "the frontend image must carry the Studio license and third-party notices",
    )


def validate_website_build_contract() -> None:
    """Keep the generated website link and source-reference check in CI."""
    package = json.loads(
        (PLATFORM_ROOT / "apps/website/package.json").read_text(encoding="utf-8")
    )
    scripts = package.get("scripts", {})
    require(
        scripts.get("validate:build") == "node scripts/validate-build.mjs",
        "the website must expose its generated-build validator as validate:build",
    )
    website_ci = (PLATFORM_ROOT / ".github/workflows/website-ci.yml").read_text(
        encoding="utf-8"
    )
    require(
        "npm run validate:build" in website_ci,
        "website CI must validate generated internal links and source references",
    )
    validator = (PLATFORM_ROOT / "apps/website/scripts/validate-build.mjs").read_text(
        encoding="utf-8"
    )
    require(
        "relative(outputRoot, resolvedTarget)" in validator
        and "!isAbsolute(outputRelativeTarget)" in validator,
        "website link validation must reject targets outside generated output",
    )


def validate_python_support_policy() -> None:
    """Keep the SDK development runtime and published compatibility explicit."""
    sdk_root = PLATFORM_ROOT / "sdks/python"
    development_version = (
        (sdk_root / ".python-version").read_text(encoding="utf-8").strip()
    )
    require(
        development_version == "3.13",
        "the Python SDK development and documentation version must be 3.13",
    )

    pyproject = tomllib.loads((sdk_root / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    require(
        project["requires-python"] == ">=3.11",
        "the Python SDK compatibility floor must remain Python 3.11",
    )
    expected_classifiers = {
        f"Programming Language :: Python :: 3.{minor}" for minor in range(11, 15)
    }
    require(
        expected_classifiers.issubset(set(project["classifiers"])),
        "the Python SDK classifiers must declare every tested Python version",
    )
    require(
        pyproject["tool"]["ruff"]["target-version"] == "py311",
        "Ruff must preserve syntax compatibility with the Python 3.11 floor",
    )

    workflow_root = PLATFORM_ROOT / ".github/workflows"
    python_ci = (workflow_root / "python-ci.yml").read_text(encoding="utf-8")
    require(
        "name: Primary health (Python 3.13)" in python_ci
        and 'python-version: "3.13"' in python_ci
        and 'python-version: ["3.11", "3.12", "3.14"]' in python_ci
        and "UV_PYTHON: ${{ matrix.python-version }}" in python_ci,
        "Python CI must pair the 3.13 primary job with the supported compatibility matrix",
    )
    python_publish = (workflow_root / "python-publish.yml").read_text(encoding="utf-8")
    python_examples = (workflow_root / "python-examples-smoke.yml").read_text(
        encoding="utf-8"
    )
    require(
        "uses: ./.github/workflows/python-ci.yml" in python_publish
        and "uses: ./.github/workflows/python-examples-smoke.yml" in python_publish
        and "needs: [sdk-validation, examples-validation, build-release]"
        in python_publish
        and "workflow_call:" in python_examples
        and "Run AI Chat infrastructure tests" in python_examples,
        "PyPI publication must wait for reusable SDK, AI Chat, and release-build validation",
    )


def validate_release_routing() -> None:
    """Keep publishers namespaced and enforce the Studio release transaction."""
    workflow_root = PLATFORM_ROOT / ".github" / "workflows"
    python_publish = (workflow_root / "python-publish.yml").read_text(encoding="utf-8")
    studio_publish = (workflow_root / "studio-docker-publish.yml").read_text(
        encoding="utf-8"
    )
    studio_validation = (workflow_root / "studio-release-validation.yml").read_text(
        encoding="utf-8"
    )
    studio_deployments = (workflow_root / "studio-deployments.yml").read_text(
        encoding="utf-8"
    )
    distribution_publisher = (
        PLATFORM_ROOT / "tooling/scripts/publish_studio_distribution.py"
    ).read_text(encoding="utf-8")
    platform_gate = (workflow_root / "platform-gate.yml").read_text(encoding="utf-8")
    evidence_upload = studio_publish[
        studio_publish.index(
            "- name: Upload release and mirror evidence"
        ) : studio_publish.index("\n  promote_floating_tags:")
    ]

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
    release_policy = (
        PLATFORM_ROOT / "tooling/scripts/validate_studio_release_policy.py"
    ).read_text(encoding="utf-8")
    require(
        'expected_tag = f"studio-v{studio_version}"' in release_policy
        and "--release-tag" in studio_validation,
        "Studio publishing must validate the exact Studio version tag",
    )
    require(
        "context: ./apps/studio" in studio_publish,
        "Studio images must build from the Studio project context",
    )
    require(
        "&& 'studio-release' || format('studio-release-rehearsal-{0}', github.run_id)"
        in studio_publish,
        "production Studio releases must use one constant global concurrency group",
    )
    require(
        "cancel-in-progress: false" in studio_publish,
        "Studio release transactions must never cancel an in-progress release",
    )
    require(
        "python3 tooling/scripts/validate_studio_release_policy.py" in studio_validation
        and "--existing-releases" in studio_validation
        and "--existing-tags" in studio_validation
        and 'gh release view "$GITHUB_REF_NAME"' in studio_validation
        and "git tag --list 'studio-v*'" in studio_validation
        and "git merge-base --is-ancestor" in studio_validation
        and "classify-images" in studio_publish,
        "Studio admission must validate GitHub releases and every fetched stable tag",
    )
    require(
        "validation:\n    name: Studio release validation\n"
        "    uses: ./.github/workflows/studio-release-validation.yml"
        in studio_publish
        and "needs: validation" in studio_publish,
        "Studio publication must wait for shared read-only release validation",
    )
    require(
        "workflow_call:" in studio_validation
        and "contents: write" not in studio_validation
        and "workflow_call:" not in studio_publish
        and "permissions:\n      contents: write" in studio_publish,
        "read-only release validation and write-capable publication must remain separate",
    )
    require(
        "run_live_smoke:" in studio_deployments
        and "if: github.event_name == 'workflow_dispatch' || inputs.run_live_smoke"
        in studio_deployments
        and "run_live_smoke: true" in studio_validation,
        "heavy local-image telemetry smoke must be manual or release-routed, never a master-push default",
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
        "environment: studio-release-production" in studio_publish,
        "final Studio GitHub release mutation must use its protected environment",
    )
    require(
        "needs: [validation, smoke_exact_release]" in studio_publish,
        "distribution publication must wait for deployment and exact-image smoke checks",
    )
    require(
        "needs: [validation, publish_distributions]" in studio_publish,
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
        "tooling/scripts/smoke_studio_distribution.py" in studio_publish
        and "--image-source registry" in studio_publish
        and "--expected-image" in studio_publish
        and "--evidence-directory /tmp/studio-h2-evidence/registry" in studio_publish
        and "test:e2e:agent-live"
        in (PLATFORM_ROOT / "tooling/scripts/smoke_studio_distribution.py").read_text(
            encoding="utf-8"
        )
        and "validate_agent_studio_e2e.py"
        in (PLATFORM_ROOT / "tooling/scripts/smoke_studio_distribution.py").read_text(
            encoding="utf-8"
        ),
        "Studio releases must smoke exact images through public Agent telemetry and browser diagnostics",
    )
    require(
        'for tag in "$VERSION" "$SOURCE_REVISION"' in studio_publish
        and "Reinspect every immutable image tag" in studio_publish,
        "Studio version and full source-revision tags must be immutable and reinspected",
    )
    require(
        "${{ github.run_attempt }}" not in studio_publish
        and "candidate-${SOURCE_REVISION}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
        in studio_publish
        and studio_publish.count("overwrite: true") == 4
        and "run_attempt: ${{ steps.attempt.outputs.run_attempt }}" in studio_validation
        and studio_publish.count("Reject partial production rerun") == 7
        and studio_publish.count(
            "ADMITTED_RUN_ATTEMPT: ${{ needs.validation.outputs.run_attempt }}"
        )
        == 7,
        "Studio release artifacts must be stable and partial reruns must fail closed",
    )
    require(
        "/tmp/junjo-release/*.json" not in evidence_upload
        and all(
            f"/tmp/junjo-release/{filename}" in evidence_upload
            for filename in (
                "minimal-export.json",
                "minimal-mirror.json",
                "vm-caddy-export.json",
                "vm-caddy-mirror.json",
            )
        )
        and "mirror-preflight.json" not in evidence_upload
        and "mirror-authorized-preflight.json" not in evidence_upload,
        "Studio distribution artifacts must contain only contract-owned evidence",
    )
    require(
        "Validate live Docker Hub immutable-tag controls" in studio_publish
        and "validate-dockerhub" in studio_publish
        and studio_publish.index("Validate live Docker Hub immutable-tag controls")
        < studio_publish.index("Build and push architecture image by digest"),
        "Studio registry mutation must wait for live immutability controls",
    )
    require(
        "JUNJO_MINIMAL_MIRROR" not in studio_publish
        and "JUNJO_VM_CADDY_MIRROR" not in studio_publish,
        "Studio release destinations must not come from mutable repository variables",
    )
    require(
        "--distribution minimal" in studio_publish
        and "--distribution vm-caddy" in studio_publish
        and 'parser.add_argument("--repository"' not in distribution_publisher
        and 'parser.add_argument("--branch"' not in distribution_publisher
        and 'parser.add_argument("--contract"' not in distribution_publisher,
        "Studio mirror publication must use contract-bound distribution identities",
    )
    require(
        "Validate all mirror destinations before minting mutation credentials"
        in studio_publish
        and "Revalidate all mirror destinations with the installation token"
        in studio_publish
        and "validate-destinations" in studio_publish
        and studio_publish.index(
            "Validate all mirror destinations before minting mutation credentials"
        )
        < studio_publish.index("Create mirror installation token")
        < studio_publish.index(
            "Revalidate all mirror destinations with the installation token"
        )
        < studio_publish.index("--export-directory /tmp/junjo-release/minimal"),
        "both mirror destinations must be validated before any mirror publication",
    )
    require(
        "uses: ./.github/workflows/platform-integrity.yml" in platform_gate
        and "name: required" not in platform_gate
        and "PLATFORM_RESULT" not in platform_gate,
        "pull requests must report platform integrity without a synthetic required gate",
    )
    forbidden_pr_workflows = (
        "python-ci.yml",
        "studio-backend-tests.yml",
        "studio-frontend-tests.yml",
        "studio-proto-staleness-check.yml",
        "studio-rest-api-contract-validation.yml",
        "studio-version-sync-check.yml",
        "telemetry-contract.yml",
        "studio-release-validation.yml",
        "studio-docker-publish.yml",
        "website-ci.yml",
    )
    require(
        all(workflow not in platform_gate for workflow in forbidden_pr_workflows)
        and "detect_ci_changes" not in platform_gate,
        "pull requests must not run component or release validation workflows",
    )
    require(
        "refs/tags/${REF_NAME}^{commit}" in studio_validation
        and "refs/tags/${GITHUB_REF_NAME}^{commit}" in studio_publish
        and "Release tag $GITHUB_REF_NAME moved" in studio_publish,
        "Studio release admission and finalization must bind the live tag target",
    )


def validate_studio_release_contract() -> None:
    """Validate the exact first-party image and distribution destinations."""
    contract_path = PLATFORM_ROOT / "tooling/studio_release_contract.json"
    contract = load_release_contract(contract_path)
    require(
        contract["completed_release_baseline"] == "0.81.1",
        "Studio's immutable pre-monorepo baseline must remain 0.81.1",
    )
    require(
        contract["dockerhub_immutable_tag_rules"]
        == [r"^[0-9]+\.[0-9]+\.[0-9]+$", r"^[0-9a-f]{40}$"],
        "Studio's Docker Hub rules must protect exact version and source-SHA tags",
    )
    require(
        contract["imported_two_part_studio_tags"]
        == [
            "studio-v0.10",
            "studio-v0.20",
            "studio-v0.30",
            "studio-v0.40",
            "studio-v0.42",
        ],
        "Studio's imported two-part tag provenance differs from the accepted contract",
    )
    require(
        contract["images"]
        == {
            "backend": {"repository": "mdrideout/junjo-ai-studio-backend"},
            "frontend": {"repository": "mdrideout/junjo-ai-studio-frontend"},
            "ingestion": {"repository": "mdrideout/junjo-ai-studio-ingestion"},
        },
        "Studio image repositories differ from the accepted release contract",
    )
    require(
        contract["distributions"]
        == {
            "minimal": {
                "canonical_source_path": "apps/studio/deployments/minimal",
                "mirror_repository": "mdrideout/junjo-ai-studio-minimal-build",
                "mirror_branch": "master",
            },
            "vm-caddy": {
                "canonical_source_path": "apps/studio/deployments/vm-caddy",
                "mirror_repository": "mdrideout/junjo-ai-studio-deployment-example",
                "mirror_branch": "master",
            },
        },
        "Studio distribution mirrors differ from the accepted release contract",
    )
    studio_version = (
        (PLATFORM_ROOT / "apps/studio/VERSION").read_text(encoding="utf-8").strip()
    )
    require(
        parse_version(studio_version) > parse_version("0.81.1"),
        "the monorepo Studio version must be greater than the 0.81.1 baseline",
    )


def validate_workflow_action_pins() -> None:
    """Require immutable commits for every external GitHub Action dependency."""
    workflow_root = PLATFORM_ROOT / ".github" / "workflows"
    workflows = sorted(workflow_root.glob("*.yml")) + sorted(
        workflow_root.glob("*.yaml")
    )
    for workflow in workflows:
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
    validate_studio_frontend_foundation()
    validate_website_build_contract()
    validate_python_support_policy()
    validate_release_routing()
    validate_studio_release_contract()
    validate_workflow_action_pins()
    validate_contract()
    print("Junjo platform repository invariants are valid.")


if __name__ == "__main__":
    main()
