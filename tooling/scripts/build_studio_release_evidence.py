#!/usr/bin/env python3
"""Validate Studio release artifacts and build deterministic release evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
from pathlib import Path
from typing import Any

from validate_studio_release_policy import (
    EXPECTED_DISTRIBUTIONS,
    EXPECTED_SERVICES,
    load_release_contract,
    parse_version,
)


GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
IMAGE_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
VERSION_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SERVICES = EXPECTED_SERVICES
DISTRIBUTIONS = EXPECTED_DISTRIBUTIONS


def require(condition: bool, message: str) -> None:
    """Raise a clear validation error when an invariant is false."""
    if not condition:
        raise RuntimeError(message)


def require_one_line(label: str, value: str) -> None:
    """Require a non-empty, whitespace-trimmed, single-line value."""
    require(bool(value), f"{label} must not be empty")
    require(value == value.strip(), f"{label} must not have surrounding whitespace")
    require(
        not any(character in value for character in "\r\n\0"),
        f"{label} must be one line",
    )


def require_git_sha(label: str, value: str) -> None:
    """Require one full lowercase Git SHA-1 object identifier."""
    require(
        GIT_SHA_PATTERN.fullmatch(value) is not None,
        f"{label} must be a full lowercase 40-character Git SHA",
    )


def require_sha256(label: str, value: object) -> str:
    """Return a validated lowercase SHA-256 hex digest."""
    require(
        isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None,
        f"{label} must be a lowercase 64-character SHA-256 digest",
    )
    return value


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    """Load one required JSON object with a path-specific error."""
    require(path.is_file(), f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{label} is not valid UTF-8 JSON: {path}") from error
    require(isinstance(value, dict), f"{label} must contain a JSON object: {path}")
    return value


def require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    """Reject incomplete or ambiguous release evidence objects."""
    actual = set(value)
    require(
        actual == expected,
        f"{label} fields must be exactly {sorted(expected)}, found {sorted(actual)}",
    )


def sha256_file(path: Path) -> str:
    """Calculate the lowercase SHA-256 digest of one file."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_archive_manifest(archive: Path) -> dict[str, Any]:
    """Read the single generated export manifest embedded in an archive."""
    try:
        with tarfile.open(archive, mode="r:gz") as release_archive:
            members = [
                member
                for member in release_archive.getmembers()
                if member.name.endswith("/EXPORT_MANIFEST.json")
            ]
            require(
                len(members) == 1,
                f"archive must contain exactly one EXPORT_MANIFEST.json: {archive}",
            )
            require(
                members[0].isfile(), f"archive export manifest is not a file: {archive}"
            )
            manifest_file = release_archive.extractfile(members[0])
            require(
                manifest_file is not None, f"could not read archive manifest: {archive}"
            )
            manifest = json.loads(manifest_file.read().decode("utf-8"))
    except (
        OSError,
        tarfile.TarError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise RuntimeError(
            f"could not read archive export manifest: {archive}"
        ) from error
    require(
        isinstance(manifest, dict),
        f"archive export manifest must be an object: {archive}",
    )
    return manifest


def validate_archive_inventory(
    archive: Path,
    manifest: dict[str, Any],
) -> None:
    """Prove every inventoried archive file has the declared path, mode, size, and hash."""
    inventory = manifest.get("inventory")
    require(isinstance(inventory, list), "export manifest inventory must be a list")
    expected: dict[str, dict[str, Any]] = {}
    for item in inventory:
        require(isinstance(item, dict), "export inventory entries must be objects")
        path = item.get("path")
        require(
            isinstance(path, str) and path, "export inventory path must be a string"
        )
        require(
            path not in expected, f"export inventory contains duplicate path: {path}"
        )
        expected[path] = item

    with tarfile.open(archive, mode="r:gz") as release_archive:
        manifest_members = [
            member
            for member in release_archive.getmembers()
            if member.name.endswith("/EXPORT_MANIFEST.json")
        ]
        require(len(manifest_members) == 1, "archive must contain one export manifest")
        archive_root = manifest_members[0].name.removesuffix("/EXPORT_MANIFEST.json")
        actual: dict[str, tarfile.TarInfo] = {}
        for member in release_archive.getmembers():
            prefix = f"{archive_root}/"
            if not member.isfile() or not member.name.startswith(prefix):
                continue
            relative_path = member.name.removeprefix(prefix)
            if relative_path == "EXPORT_MANIFEST.json":
                continue
            require(
                relative_path not in actual,
                f"archive contains duplicate file: {relative_path}",
            )
            actual[relative_path] = member

        require(
            set(actual) == set(expected),
            "archive files do not exactly match the export inventory",
        )
        for path, item in expected.items():
            member = actual[path]
            content_file = release_archive.extractfile(member)
            require(content_file is not None, f"could not read archive file: {path}")
            content = content_file.read()
            require(item.get("size") == len(content), f"archive size differs: {path}")
            require(
                item.get("mode") == f"{member.mode:04o}",
                f"archive mode differs: {path}",
            )
            require(
                item.get("sha256") == hashlib.sha256(content).hexdigest(),
                f"archive content hash differs: {path}",
            )


def read_image_evidence(
    *,
    image_directory: Path,
    image_contracts: dict[str, Any],
    studio_version: str,
    source_revision: str,
) -> dict[str, dict[str, object]]:
    """Validate each published immutable image tag and its reinspected digest."""
    require(
        image_directory.is_dir(),
        f"image evidence directory is missing: {image_directory}",
    )
    expected_files = {f"{service}.json" for service in SERVICES}
    actual_files = {
        path.relative_to(image_directory).as_posix()
        for path in image_directory.rglob("*")
        if path.is_file()
    }
    require(
        actual_files == expected_files,
        "image evidence files must be exactly "
        f"{sorted(expected_files)}, found {sorted(actual_files)}",
    )
    image_evidence: dict[str, dict[str, object]] = {}
    for service in SERVICES:
        report = load_json_object(
            image_directory / f"{service}.json",
            f"{service} image evidence",
        )
        require_exact_keys(
            report,
            {
                "schema_version",
                "service",
                "repository",
                "studio_version",
                "source_revision",
                "digest",
                "tags",
            },
            f"{service} image evidence",
        )
        expected_repository = image_contracts[service]["repository"]
        require(
            report["schema_version"] == 1, f"{service} image evidence schema must be 1"
        )
        require(
            report["service"] == service,
            f"{service} image evidence names the wrong service",
        )
        require(
            report["repository"] == expected_repository,
            f"{service} image repository does not match the release contract",
        )
        require(
            report["studio_version"] == studio_version,
            f"{service} image version does not match the release",
        )
        require(
            report["source_revision"] == source_revision,
            f"{service} image source revision does not match the release",
        )
        digest = report["digest"]
        require(
            isinstance(digest, str)
            and IMAGE_DIGEST_PATTERN.fullmatch(digest) is not None,
            f"{service} image digest must be sha256 followed by 64 lowercase hex characters",
        )
        tags = report["tags"]
        require(isinstance(tags, dict), f"{service} image tags must be an object")
        require_exact_keys(
            tags, {"version", "source_revision"}, f"{service} image tags"
        )
        expected_tags = {
            "version": studio_version,
            "source_revision": source_revision,
        }
        for role, expected_name in expected_tags.items():
            tag = tags[role]
            require(isinstance(tag, dict), f"{service} {role} tag must be an object")
            require_exact_keys(tag, {"name", "digest"}, f"{service} {role} tag")
            require(
                tag["name"] == expected_name,
                f"{service} {role} tag has the wrong name",
            )
            require(
                tag["digest"] == digest,
                f"{service} {role} tag does not resolve to the release digest",
            )
        image_evidence[service] = report
    return image_evidence


def validate_distribution(
    *,
    name: str,
    distribution_contract: dict[str, Any],
    evidence_directory: Path,
    source_repository: str,
    source_revision: str,
    studio_version: str,
) -> dict[str, object]:
    """Validate one export archive, export report, and mirror publication report."""
    export_report = load_json_object(
        evidence_directory / f"{name}-export.json",
        f"{name} export report",
    )
    require(
        export_report.get("distribution") == name,
        f"{name} export report has the wrong distribution",
    )

    expected_archive_name = f"junjo-ai-studio-{name}-{studio_version}.tar.gz"
    archive = evidence_directory / expected_archive_name
    require(archive.is_file(), f"{name} release archive is missing: {archive}")
    reported_archive = export_report.get("archive")
    require(
        isinstance(reported_archive, str)
        and Path(reported_archive).name == expected_archive_name,
        f"{name} export report names the wrong archive",
    )
    archive_sha256 = require_sha256(
        f"{name} archive_sha256", export_report.get("archive_sha256")
    )
    require(
        sha256_file(archive) == archive_sha256,
        f"{name} archive content does not match archive_sha256",
    )
    tree_sha256 = require_sha256(
        f"{name} tree_sha256", export_report.get("tree_sha256")
    )

    source = export_report.get("source")
    require(isinstance(source, dict), f"{name} export report source must be an object")
    canonical_source_path = distribution_contract["canonical_source_path"]
    mirror_repository = distribution_contract["mirror_repository"]
    mirror_branch = distribution_contract["mirror_branch"]
    expected_source = {
        "schema_version": 1,
        "distribution": name,
        "source_repository": source_repository,
        "canonical_source_path": canonical_source_path,
        "source_revision": source_revision,
        "studio_version": studio_version,
    }
    for key, expected in expected_source.items():
        require(
            source.get(key) == expected,
            f"{name} export report source {key} does not match the release",
        )

    manifest = read_archive_manifest(archive)
    require(
        manifest.get("schema_version") == 1,
        f"{name} export manifest schema_version must be 1",
    )
    require(
        manifest.get("source") == source,
        f"{name} archive source does not match its export report",
    )
    require(
        manifest.get("tree_sha256") == tree_sha256,
        f"{name} archive tree hash does not match its export report",
    )
    inventory = manifest.get("inventory")
    require(
        isinstance(inventory, list), f"{name} export manifest inventory must be a list"
    )
    calculated_tree_sha256 = hashlib.sha256(
        json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    require(
        calculated_tree_sha256 == tree_sha256,
        f"{name} export inventory does not match tree_sha256",
    )
    validate_archive_inventory(archive, manifest)

    mirror_report = load_json_object(
        evidence_directory / f"{name}-mirror.json",
        f"{name} mirror report",
    )
    require_exact_keys(
        mirror_report,
        {
            "distribution",
            "repository",
            "branch",
            "commit",
            "source_revision",
            "changed",
            "tree_sha256",
        },
        f"{name} mirror report",
    )
    require(
        mirror_report.get("distribution") == name,
        f"{name} mirror report names the wrong distribution",
    )
    require(
        mirror_report.get("repository") == mirror_repository,
        f"{name} mirror repository does not match the release contract",
    )
    require(
        mirror_report.get("branch") == mirror_branch,
        f"{name} mirror branch does not match the release contract",
    )
    mirror_commit = mirror_report.get("commit")
    require(isinstance(mirror_commit, str), f"{name} mirror commit must be a string")
    require_git_sha(f"{name} mirror commit", mirror_commit)
    require(
        mirror_report.get("source_revision") == source_revision,
        f"{name} mirror source revision does not match the release",
    )
    require(
        mirror_report.get("tree_sha256") == tree_sha256,
        f"{name} mirror tree hash does not match the export",
    )
    require(
        isinstance(mirror_report.get("changed"), bool),
        f"{name} mirror changed flag must be a boolean",
    )

    return {
        "archive_sha256": archive_sha256,
        "tree_sha256": tree_sha256,
        "mirror": {
            "repository": mirror_repository,
            "branch": mirror_branch,
            "commit": mirror_commit,
        },
        "source": source,
    }


def build_release_evidence(
    *,
    studio_version: str,
    release_tag: str,
    source_repository: str,
    source_revision: str,
    workflow_url: str,
    image_directory: Path,
    distribution_directory: Path,
) -> dict[str, object]:
    """Validate every release input and return the complete evidence document."""
    require(
        VERSION_PATTERN.fullmatch(studio_version) is not None,
        "Studio version must be a stable X.Y.Z version",
    )
    require(
        release_tag == f"studio-v{studio_version}",
        f"release tag must be studio-v{studio_version}",
    )
    require_one_line("source repository", source_repository)
    require_one_line("workflow URL", workflow_url)
    require_git_sha("source revision", source_revision)
    contract = load_release_contract()
    baseline = contract["completed_release_baseline"]
    require(isinstance(baseline, str), "completed release baseline must be a string")
    require(
        parse_version(studio_version) > parse_version(baseline),
        f"Studio version must be greater than completed baseline {baseline}",
    )
    require(
        distribution_directory.is_dir(),
        f"distribution evidence directory is missing: {distribution_directory}",
    )
    expected_distribution_files = {
        filename
        for name in DISTRIBUTIONS
        for filename in (
            f"{name}-export.json",
            f"{name}-mirror.json",
            f"junjo-ai-studio-{name}-{studio_version}.tar.gz",
        )
    }
    actual_distribution_files = {
        path.relative_to(distribution_directory).as_posix()
        for path in distribution_directory.rglob("*")
        if path.is_file()
    }
    require(
        actual_distribution_files == expected_distribution_files,
        "distribution evidence files must be exactly "
        f"{sorted(expected_distribution_files)}, "
        f"found {sorted(actual_distribution_files)}",
    )

    image_contracts = contract["images"]
    distribution_contracts = contract["distributions"]
    distributions = {
        name: validate_distribution(
            name=name,
            distribution_contract=distribution_contracts[name],
            evidence_directory=distribution_directory,
            source_repository=source_repository,
            source_revision=source_revision,
            studio_version=studio_version,
        )
        for name in DISTRIBUTIONS
    }
    return {
        "schema_version": 1,
        "studio_version": studio_version,
        "release_tag": release_tag,
        "source_repository": source_repository,
        "source_revision": source_revision,
        "workflow_url": workflow_url,
        "images": read_image_evidence(
            image_directory=image_directory,
            image_contracts=image_contracts,
            studio_version=studio_version,
            source_revision=source_revision,
        ),
        "distributions": distributions,
    }


def build_release_notes(evidence: dict[str, object]) -> str:
    """Render concise deterministic Markdown notes from validated evidence."""
    images = evidence["images"]
    distributions = evidence["distributions"]
    require(isinstance(images, dict), "images must be an object")
    require(isinstance(distributions, dict), "distributions must be an object")
    lines = [
        f"Validated Junjo AI Studio {evidence['studio_version']} release.",
        "",
        f"Canonical source: {evidence['source_repository']}@{evidence['source_revision']}",
        f"Workflow: {evidence['workflow_url']}",
        "",
        "Immutable image tags:",
    ]
    for service in SERVICES:
        image = images[service]
        require(isinstance(image, dict), f"{service} image evidence must be an object")
        lines.append(
            f"- {service}: `{image['repository']}@{image['digest']}` "
            f"(tags `{image['studio_version']}` and `{image['source_revision']}`)"
        )
    lines.extend(("", "Deployment distributions:"))
    for name in DISTRIBUTIONS:
        item = distributions[name]
        require(
            isinstance(item, dict), f"{name} distribution evidence must be an object"
        )
        lines.append(
            f"- {name}: archive `{item['archive_sha256']}`, "
            f"tree `{item['tree_sha256']}`, mirror "
            f"`{item['mirror']['repository']}:{item['mirror']['branch']}@"
            f"{item['mirror']['commit']}`"
        )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit release-evidence command-line interface."""
    parser = argparse.ArgumentParser(
        description="Validate Studio release artifacts and write release evidence."
    )
    parser.add_argument("--studio-version", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--source-repository", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--workflow-url", required=True)
    parser.add_argument("--image-directory", type=Path, required=True)
    parser.add_argument("--distribution-directory", type=Path, required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--notes-output", type=Path, required=True)
    return parser


def main() -> int:
    """Validate release inputs and write deterministic JSON and Markdown files."""
    args = build_parser().parse_args()
    evidence = build_release_evidence(
        studio_version=args.studio_version,
        release_tag=args.release_tag,
        source_repository=args.source_repository,
        source_revision=args.source_revision,
        workflow_url=args.workflow_url,
        image_directory=args.image_directory.resolve(),
        distribution_directory=args.distribution_directory.resolve(),
    )
    evidence_output = args.evidence_output.resolve()
    notes_output = args.notes_output.resolve()
    evidence_output.parent.mkdir(parents=True, exist_ok=True)
    notes_output.parent.mkdir(parents=True, exist_ok=True)
    evidence_output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    notes_output.write_text(build_release_notes(evidence), encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
