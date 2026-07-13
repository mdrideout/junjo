#!/usr/bin/env python3
"""Validate the repository-owned Studio release contract and admission policy."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT_PATH = REPOSITORY_ROOT / "tooling" / "studio_release_contract.json"
VERSION_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
TWO_PART_STUDIO_TAG_PATTERN = re.compile(
    r"^studio-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
REPOSITORY_PATTERN = re.compile(r"^[a-z0-9_.-]+/[a-z0-9_.-]+$")
EXPECTED_SERVICES = ("backend", "frontend", "ingestion")
EXPECTED_DISTRIBUTIONS = ("minimal", "vm-caddy")


@dataclass(frozen=True)
class ReleaseStateDecision:
    """One explicit release state and the invariant that selected it."""

    state: str
    reason: str


def require(condition: bool, message: str) -> None:
    """Raise a release-policy error when an invariant is false."""
    if not condition:
        raise RuntimeError(message)


def require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    """Reject missing and unknown contract fields."""
    actual = set(value)
    require(
        actual == expected,
        f"{label} fields must be exactly {sorted(expected)}, found {sorted(actual)}",
    )


def parse_version(value: str, label: str = "Studio version") -> tuple[int, int, int]:
    """Parse one stable X.Y.Z version into a comparison tuple."""
    match = VERSION_PATTERN.fullmatch(value)
    require(match is not None, f"{label} must be a stable X.Y.Z version")
    return tuple(int(part) for part in match.groups())


def require_git_sha(value: str, label: str) -> None:
    """Require a full lowercase Git SHA-1 identifier."""
    require(
        GIT_SHA_PATTERN.fullmatch(value) is not None,
        f"{label} must be a full lowercase 40-character Git SHA",
    )


def load_release_contract(path: Path = DEFAULT_CONTRACT_PATH) -> dict[str, Any]:
    """Load and strictly validate the complete release identity contract."""
    require(path.is_file(), f"Studio release contract is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Studio release contract is not valid UTF-8 JSON: {path}"
        ) from error
    require(isinstance(value, dict), "Studio release contract must be a JSON object")
    require_exact_keys(
        value,
        {
            "schema_version",
            "completed_release_baseline",
            "dockerhub_immutable_tag_rules",
            "imported_two_part_studio_tags",
            "images",
            "distributions",
        },
        "Studio release contract",
    )
    require(
        value["schema_version"] == 1, "Studio release contract schema_version must be 1"
    )
    require(
        isinstance(value["completed_release_baseline"], str),
        "completed_release_baseline must be a string",
    )
    parse_version(value["completed_release_baseline"], "completed release baseline")

    immutable_tag_rules = value["dockerhub_immutable_tag_rules"]
    require(
        isinstance(immutable_tag_rules, list)
        and all(isinstance(rule, str) for rule in immutable_tag_rules),
        "dockerhub_immutable_tag_rules must be a list of strings",
    )
    require(
        immutable_tag_rules
        == [r"^[0-9]+\.[0-9]+\.[0-9]+$", r"^[0-9a-f]{40}$"],
        "Docker Hub immutable rules must protect stable versions and full Git SHAs",
    )

    imported_tags = value["imported_two_part_studio_tags"]
    require(
        isinstance(imported_tags, list)
        and all(isinstance(tag, str) for tag in imported_tags),
        "imported_two_part_studio_tags must be a list of strings",
    )
    require(
        len(imported_tags) == len(set(imported_tags)),
        "imported two-part Studio tags must be unique",
    )
    imported_versions: list[tuple[int, int]] = []
    for tag in imported_tags:
        match = TWO_PART_STUDIO_TAG_PATTERN.fullmatch(tag)
        require(
            match is not None,
            f"imported historical Studio tag must be exactly studio-vX.Y: {tag}",
        )
        imported_versions.append(tuple(int(part) for part in match.groups()))
    require(
        imported_versions == sorted(imported_versions),
        "imported two-part Studio tags must be in ascending version order",
    )

    images = value["images"]
    require(
        isinstance(images, dict), "Studio release contract images must be an object"
    )
    require_exact_keys(images, set(EXPECTED_SERVICES), "Studio release contract images")
    for service in EXPECTED_SERVICES:
        image = images[service]
        require(isinstance(image, dict), f"{service} image contract must be an object")
        require_exact_keys(image, {"repository"}, f"{service} image contract")
        repository = image["repository"]
        require(
            isinstance(repository, str)
            and REPOSITORY_PATTERN.fullmatch(repository) is not None,
            f"{service} image repository must be an owner/repository name",
        )

    distributions = value["distributions"]
    require(
        isinstance(distributions, dict),
        "Studio release contract distributions must be an object",
    )
    require_exact_keys(
        distributions,
        set(EXPECTED_DISTRIBUTIONS),
        "Studio release contract distributions",
    )
    seen_mirrors: set[tuple[str, str]] = set()
    for name in EXPECTED_DISTRIBUTIONS:
        distribution = distributions[name]
        require(
            isinstance(distribution, dict),
            f"{name} distribution contract must be an object",
        )
        require_exact_keys(
            distribution,
            {"canonical_source_path", "mirror_repository", "mirror_branch"},
            f"{name} distribution contract",
        )
        source_path = distribution["canonical_source_path"]
        require(
            isinstance(source_path, str)
            and source_path == f"apps/studio/deployments/{name}",
            f"{name} canonical source path must be apps/studio/deployments/{name}",
        )
        repository = distribution["mirror_repository"]
        branch = distribution["mirror_branch"]
        require(
            isinstance(repository, str)
            and REPOSITORY_PATTERN.fullmatch(repository) is not None,
            f"{name} mirror repository must be an owner/repository name",
        )
        require(
            isinstance(branch, str)
            and branch == branch.strip()
            and bool(branch)
            and not any(character in branch for character in "\r\n\0"),
            f"{name} mirror branch must be one non-empty line",
        )
        mirror = (repository, branch)
        require(mirror not in seen_mirrors, "distribution mirrors must be distinct")
        seen_mirrors.add(mirror)
    return value


def load_existing_releases(path: Path) -> list[dict[str, Any]]:
    """Load the release list emitted by ``gh release list --json``."""
    require(path.is_file(), f"existing release list is missing: {path}")
    try:
        releases = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"existing release list is not valid UTF-8 JSON: {path}"
        ) from error
    require(isinstance(releases, list), "existing release list must be a JSON array")
    for release in releases:
        require(isinstance(release, dict), "existing release entries must be objects")
        require(
            isinstance(release.get("tagName"), str),
            "existing release tagName must be a string",
        )
        require(
            isinstance(release.get("isDraft"), bool),
            "existing release isDraft must be a boolean",
        )
    return releases


def load_existing_tags(path: Path) -> list[str]:
    """Load the fetched stable Studio tag names used for forward-only admission."""
    require(path.is_file(), f"existing tag list is missing: {path}")
    try:
        tags = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"existing tag list is not valid UTF-8 JSON: {path}"
        ) from error
    require(isinstance(tags, list), "existing tag list must be a JSON array")
    require(
        all(isinstance(tag, str) for tag in tags),
        "existing tag names must be strings",
    )
    require(len(tags) == len(set(tags)), "existing tag names must be unique")
    return tags


def observed_studio_version(
    tag: str,
    *,
    imported_two_part_tags: set[str],
    label: str,
) -> tuple[int, int, int] | None:
    """Parse a canonical tag or identify one exact imported historical tag."""
    if tag in imported_two_part_tags:
        return None
    return parse_version(tag.removeprefix("studio-v"), label)


def classify_release_admission(
    *,
    contract: dict[str, Any],
    studio_version: str,
    mode: str,
    release_tag: str | None,
    source_revision: str,
    source_is_on_master: bool,
    existing_releases: list[dict[str, Any]],
    existing_tags: list[str],
) -> ReleaseStateDecision:
    """Classify immutable release identity before any publication mutation."""
    require(
        mode in {"production", "dry-run"}, "release mode must be production or dry-run"
    )
    candidate = parse_version(studio_version)
    baseline_value = contract["completed_release_baseline"]
    require(
        isinstance(baseline_value, str), "completed release baseline must be a string"
    )
    baseline = parse_version(baseline_value, "completed release baseline")
    require_git_sha(source_revision, "source revision")
    require(
        isinstance(source_is_on_master, bool), "source_is_on_master must be a boolean"
    )

    expected_tag = f"studio-v{studio_version}"
    if release_tag not in {None, expected_tag}:
        return ReleaseStateDecision("stale", f"release tag must be {expected_tag}")
    if mode == "production" and release_tag is None:
        return ReleaseStateDecision("stale", f"release tag must be {expected_tag}")
    if mode == "dry-run" and release_tag is not None:
        return ReleaseStateDecision(
            "stale", "dry-run validation must not supply a release tag"
        )
    if candidate <= baseline:
        return ReleaseStateDecision(
            "stale",
            f"Studio version must be greater than completed baseline {baseline_value}",
        )
    if mode == "production" and not source_is_on_master:
        return ReleaseStateDecision(
            "stale",
            "production release revision must be reachable from origin/master",
        )

    imported_tags_value = contract["imported_two_part_studio_tags"]
    require(
        isinstance(imported_tags_value, list),
        "imported_two_part_studio_tags must be a list",
    )
    imported_tags = set(imported_tags_value)
    completed_versions: list[tuple[tuple[int, int, int], str]] = [
        (baseline, baseline_value)
    ]
    for release in existing_releases:
        tag = release["tagName"]
        if tag == expected_tag:
            if release["isDraft"]:
                return ReleaseStateDecision(
                    "stale", f"draft GitHub release {expected_tag} already exists"
                )
            return ReleaseStateDecision(
                "completed", f"GitHub release {expected_tag} already exists"
            )
        if not tag.startswith("studio-v"):
            continue
        version = observed_studio_version(
            tag,
            imported_two_part_tags=imported_tags,
            label=f"existing Studio release tag {tag}",
        )
        if version is not None and not release["isDraft"]:
            completed_versions.append((version, tag.removeprefix("studio-v")))

    existing_tag_versions: list[tuple[tuple[int, int, int], str]] = []
    for tag in existing_tags:
        if not tag.startswith("studio-v") or tag == expected_tag:
            continue
        version = observed_studio_version(
            tag,
            imported_two_part_tags=imported_tags,
            label=f"existing Studio Git tag {tag}",
        )
        if version is not None:
            existing_tag_versions.append((version, tag.removeprefix("studio-v")))

    latest_version, latest_value = max(completed_versions + existing_tag_versions)
    if candidate <= latest_version:
        return ReleaseStateDecision(
            "stale",
            "Studio version must be greater than latest completed release or stable tag "
            f"{latest_value}",
        )
    return ReleaseStateDecision(
        "new", "release identity is new and eligible for immutable-image preflight"
    )


def load_immutable_image_state(path: Path) -> dict[str, Any]:
    """Load one workflow-produced registry observation for pure classification."""
    require(path.is_file(), f"immutable image state is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"immutable image state is not valid UTF-8 JSON: {path}"
        ) from error
    require(isinstance(value, dict), "immutable image state must be a JSON object")
    return value


def load_dockerhub_repository_settings(path: Path) -> dict[str, Any]:
    """Load one live Docker Hub repository-settings response."""
    require(path.is_file(), f"Docker Hub repository settings are missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Docker Hub repository settings are not valid UTF-8 JSON: {path}"
        ) from error
    require(
        isinstance(value, dict),
        f"Docker Hub repository settings must be a JSON object: {path}",
    )
    return value


def validate_dockerhub_controls(
    *, contract: dict[str, Any], settings_directory: Path
) -> dict[str, Any]:
    """Prove live registry rules make exact tags immutable and floating tags mutable."""
    require(
        settings_directory.is_dir(),
        f"Docker Hub settings directory is missing: {settings_directory}",
    )
    expected_rules = contract["dockerhub_immutable_tag_rules"]
    repositories: list[dict[str, Any]] = []
    for service in EXPECTED_SERVICES:
        repository = contract["images"][service]["repository"]
        namespace, name = repository.split("/", maxsplit=1)
        settings = load_dockerhub_repository_settings(
            settings_directory / f"{service}.json"
        )
        require(
            settings.get("namespace") == namespace and settings.get("name") == name,
            f"{service} Docker Hub settings identity does not match {repository}",
        )
        immutable = settings.get("immutable_tags_settings")
        require(
            isinstance(immutable, dict),
            f"{service} Docker Hub response has no immutable_tags_settings object",
        )
        require(
            immutable.get("enabled") is True,
            f"{service} Docker Hub immutable tags must be enabled",
        )
        rules = immutable.get("rules")
        require(
            isinstance(rules, list) and all(isinstance(rule, str) for rule in rules),
            f"{service} Docker Hub immutable tag rules must be a list of strings",
        )
        require(
            len(rules) == len(set(rules)) and set(rules) == set(expected_rules),
            f"{service} Docker Hub immutable rules must exactly match the release contract",
        )
        repositories.append(
            {
                "service": service,
                "repository": repository,
                "immutable_tag_rules": sorted(rules),
            }
        )
    return {"schema_version": 1, "repositories": repositories}


def classify_immutable_image_state(
    *, contract: dict[str, Any], state: dict[str, Any]
) -> ReleaseStateDecision:
    """Classify a new or resumable release from exact immutable registry tags."""
    require_exact_keys(
        state,
        {"schema_version", "studio_version", "source_revision", "images"},
        "immutable image state",
    )
    require(state["schema_version"] == 1, "immutable image state schema must be 1")
    require(
        isinstance(state["studio_version"], str),
        "immutable image state Studio version must be a string",
    )
    parse_version(state["studio_version"], "immutable image state Studio version")
    require(
        isinstance(state["source_revision"], str),
        "immutable image state source revision must be a string",
    )
    require_git_sha(state["source_revision"], "immutable image state source revision")
    images = state["images"]
    require(isinstance(images, dict), "immutable image state images must be an object")
    require_exact_keys(images, set(EXPECTED_SERVICES), "immutable image state images")

    observed_count = 0
    mismatches: list[str] = []
    for service in EXPECTED_SERVICES:
        image = images[service]
        require(isinstance(image, dict), f"{service} immutable image state must be an object")
        require_exact_keys(
            image,
            {"repository", "candidate_digest", "tags"},
            f"{service} immutable image state",
        )
        require(
            image["repository"] == contract["images"][service]["repository"],
            f"{service} immutable image repository does not match the release contract",
        )
        candidate_digest = image["candidate_digest"]
        require(
            isinstance(candidate_digest, str)
            and IMAGE_DIGEST_PATTERN.fullmatch(candidate_digest) is not None,
            f"{service} candidate digest must be a sha256 image digest",
        )
        tags = image["tags"]
        require(isinstance(tags, dict), f"{service} immutable tags must be an object")
        require_exact_keys(
            tags, {"version", "source_revision"}, f"{service} immutable tags"
        )
        for role in ("version", "source_revision"):
            digest = tags[role]
            require(
                digest is None
                or (
                    isinstance(digest, str)
                    and IMAGE_DIGEST_PATTERN.fullmatch(digest) is not None
                ),
                f"{service} {role} digest must be null or a sha256 image digest",
            )
            if digest is None:
                continue
            observed_count += 1
            if digest != candidate_digest:
                mismatches.append(f"{service}:{role}")

    if mismatches:
        return ReleaseStateDecision(
            "stale",
            "immutable release tags differ from the rebuilt candidate: "
            + ", ".join(mismatches),
        )
    if observed_count:
        return ReleaseStateDecision(
            "resume", "all pre-existing immutable tags match the rebuilt candidate"
        )
    return ReleaseStateDecision("new", "no immutable release tags exist")


def validate_release_policy(
    *,
    contract: dict[str, Any],
    studio_version: str,
    mode: str,
    release_tag: str | None,
    source_revision: str,
    source_is_on_master: bool,
    existing_releases: list[dict[str, Any]],
    existing_tags: list[str],
) -> dict[str, str]:
    """Validate release admission and return stable workflow outputs."""
    decision = classify_release_admission(
        contract=contract,
        studio_version=studio_version,
        mode=mode,
        release_tag=release_tag,
        source_revision=source_revision,
        source_is_on_master=source_is_on_master,
        existing_releases=existing_releases,
        existing_tags=existing_tags,
    )
    require(
        decision.state == "new",
        f"release state {decision.state}: {decision.reason}",
    )
    return {
        "version": studio_version,
        "major_minor": ".".join(studio_version.split(".")[:2]),
        "source_revision": source_revision,
        "production": "true" if mode == "production" else "false",
        "release_state": decision.state,
    }


def append_github_outputs(path: Path, outputs: dict[str, str]) -> None:
    """Append validated single-line values to a GitHub output file."""
    with path.open("a", encoding="utf-8") as output:
        for name, value in outputs.items():
            output.write(f"{name}={value}\n")


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit policy-validation CLI."""
    parser = argparse.ArgumentParser(
        description="Validate Studio release admission policy."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    admission = commands.add_parser("admit", help="Classify release admission.")
    admission.add_argument("--studio-version", required=True)
    admission.add_argument("--mode", choices=("production", "dry-run"), required=True)
    admission.add_argument("--release-tag")
    admission.add_argument("--source-revision", required=True)
    admission.add_argument("--source-is-on-master", action="store_true")
    admission.add_argument("--existing-releases", type=Path, required=True)
    admission.add_argument("--existing-tags", type=Path, required=True)
    admission.add_argument("--github-output", type=Path)
    immutable = commands.add_parser(
        "classify-images", help="Classify exact immutable registry tag state."
    )
    immutable.add_argument("--state", type=Path, required=True)
    immutable.add_argument("--github-output", type=Path)
    dockerhub = commands.add_parser(
        "validate-dockerhub",
        help="Validate live Docker Hub immutable-tag controls.",
    )
    dockerhub.add_argument("--settings-directory", type=Path, required=True)
    return parser


def main() -> int:
    """Validate policy, print JSON, and optionally write GitHub outputs."""
    args = build_parser().parse_args()
    contract = load_release_contract()
    if args.command == "admit":
        outputs = validate_release_policy(
            contract=contract,
            studio_version=args.studio_version,
            mode=args.mode,
            release_tag=args.release_tag,
            source_revision=args.source_revision,
            source_is_on_master=args.source_is_on_master,
            existing_releases=load_existing_releases(args.existing_releases.resolve()),
            existing_tags=load_existing_tags(args.existing_tags.resolve()),
        )
    elif args.command == "classify-images":
        decision = classify_immutable_image_state(
            contract=contract,
            state=load_immutable_image_state(args.state.resolve()),
        )
        require(
            decision.state in {"new", "resume"},
            f"release state {decision.state}: {decision.reason}",
        )
        outputs = {"release_state": decision.state}
    else:
        outputs = validate_dockerhub_controls(
            contract=contract,
            settings_directory=args.settings_directory.resolve(),
        )
    if getattr(args, "github_output", None) is not None:
        append_github_outputs(args.github_output.resolve(), outputs)
    print(json.dumps(outputs, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
