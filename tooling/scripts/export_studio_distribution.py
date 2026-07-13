#!/usr/bin/env python3
"""Build a deterministic Studio deployment directory and release archive."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, overload


DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SOURCE_REPOSITORY = "https://github.com/mdrideout/junjo"
GENERATED_NOTICE = "GENERATED_SOURCE.md"
MANIFEST = "EXPORT_MANIFEST.json"
GENERATED_NAMES = {GENERATED_NOTICE, MANIFEST}

FORBIDDEN_NAMES = {
    ".env",
    ".env.bak",
    ".DS_Store",
    ".dbdata",
    ".certs",
    ".git",
    ".gitleaks",
    ".cache",
    ".coverage",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "site",
    "target",
    "tmp",
    "venv",
    "wheels",
}
FORBIDDEN_SUFFIXES = {
    ".cer",
    ".cert",
    ".crt",
    ".db",
    ".der",
    ".egg-info",
    ".env",
    ".jks",
    ".kdbx",
    ".keystore",
    ".key",
    ".log",
    ".p12",
    ".p7b",
    ".p7c",
    ".pem",
    ".pfx",
    ".pyc",
    ".sqlite",
    ".sqlite3",
}
FORBIDDEN_KEY_NAMES = {"id_dsa", "id_ecdsa", "id_ed25519", "id_rsa"}
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


@dataclass(frozen=True)
class Distribution:
    """Describe one canonical Studio distribution and its release name."""

    name: str
    canonical_path: PurePosixPath
    archive_name_prefix: str
    requires_compatible_sdk_version: bool


DISTRIBUTIONS = {
    "minimal": Distribution(
        name="minimal",
        canonical_path=PurePosixPath("apps/studio/deployments/minimal"),
        archive_name_prefix="junjo-ai-studio-minimal",
        requires_compatible_sdk_version=True,
    ),
    "vm-caddy": Distribution(
        name="vm-caddy",
        canonical_path=PurePosixPath("apps/studio/deployments/vm-caddy"),
        archive_name_prefix="junjo-ai-studio-vm-caddy",
        requires_compatible_sdk_version=True,
    ),
}


@dataclass(frozen=True)
class TrackedFile:
    """Describe one file stored in the selected Git revision."""

    relative_path: PurePosixPath
    object_id: str
    mode: int
    content: bytes


def require(condition: bool, message: str) -> None:
    """Raise a clear export error when an invariant is false."""
    if not condition:
        raise RuntimeError(message)


@overload
def run_git(
    repository_root: Path,
    arguments: list[str],
    *,
    text: Literal[False] = False,
) -> bytes: ...


@overload
def run_git(
    repository_root: Path,
    arguments: list[str],
    *,
    text: Literal[True],
) -> str: ...


def run_git(
    repository_root: Path, arguments: list[str], *, text: bool = False
) -> bytes | str:
    """Run a read-only Git command and include its error output on failure."""
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=text,
        )
    except FileNotFoundError as error:
        raise RuntimeError("required command is unavailable: git") from error
    except subprocess.CalledProcessError as error:
        stderr = error.stderr.strip() if error.stderr else ""
        raise RuntimeError(
            f"Git command failed ({' '.join(arguments)}): {stderr}"
        ) from error
    return result.stdout


def validate_metadata_value(label: str, value: str) -> None:
    """Reject metadata that could corrupt the generated notice or manifest."""
    require(bool(value.strip()), f"{label} must not be empty")
    require(value == value.strip(), f"{label} must not have surrounding whitespace")
    require(
        not any(character in value for character in "\r\n\0"),
        f"{label} must be one line",
    )


def resolve_revision(repository_root: Path, revision: str) -> str:
    """Resolve a caller-supplied revision to one exact commit SHA."""
    validate_metadata_value("source revision", revision)
    resolved = run_git(
        repository_root,
        ["rev-parse", "--verify", f"{revision}^{{commit}}"],
        text=True,
    )
    require(isinstance(resolved, str), "Git revision output must be text")
    commit = resolved.strip()
    require(
        bool(re.fullmatch(r"[0-9a-f]{40,64}", commit)),
        "Git returned an invalid commit SHA",
    )
    return commit


def read_git_blob(repository_root: Path, object_id: str) -> bytes:
    """Read one blob directly from Git without consulting the working tree."""
    content = run_git(repository_root, ["cat-file", "blob", object_id])
    require(isinstance(content, bytes), "Git blob output must be bytes")
    return content


def tracked_files_at_revision(
    repository_root: Path,
    revision: str,
    distribution: Distribution,
) -> list[TrackedFile]:
    """Load only committed distribution files from one exact source revision."""
    output = run_git(
        repository_root,
        [
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            revision,
            "--",
            str(distribution.canonical_path),
        ],
    )
    require(isinstance(output, bytes), "Git tree output must be bytes")
    files: list[TrackedFile] = []
    prefix = f"{distribution.canonical_path}/"
    for record in output.split(b"\0"):
        if not record:
            continue
        metadata, encoded_path = record.split(b"\t", maxsplit=1)
        encoded_mode, object_type, encoded_object_id = metadata.split(b" ", maxsplit=2)
        repository_path = encoded_path.decode("utf-8")
        require(
            repository_path.startswith(prefix),
            f"unexpected Git path: {repository_path}",
        )
        relative_path = PurePosixPath(repository_path.removeprefix(prefix))
        require(object_type == b"blob", f"unsupported Git object at {repository_path}")
        git_mode = encoded_mode.decode("ascii")
        require(
            git_mode in {"100644", "100755"},
            f"only regular tracked files may be exported: {repository_path} has mode {git_mode}",
        )
        mode = 0o755 if git_mode == "100755" else 0o644
        object_id = encoded_object_id.decode("ascii")
        files.append(
            TrackedFile(
                relative_path=relative_path,
                object_id=object_id,
                mode=mode,
                content=read_git_blob(repository_root, object_id),
            )
        )
    require(
        bool(files),
        f"no tracked files found at {distribution.canonical_path} in {revision}",
    )
    return sorted(files, key=lambda item: str(item.relative_path))


def forbidden_reason(path: PurePosixPath) -> str | None:
    """Return why an export path is unsafe, or ``None`` when it is allowed."""
    for part in path.parts:
        if part in FORBIDDEN_NAMES:
            return f"forbidden runtime or cache path component: {part}"
    name = path.name
    if name.startswith(".env.") and name != ".env.example":
        return f"forbidden environment file: {name}"
    if name in FORBIDDEN_KEY_NAMES:
        return f"forbidden private key filename: {name}"
    if Path(name).suffix.lower() in FORBIDDEN_SUFFIXES:
        return (
            f"forbidden secret, runtime, or cache suffix: {Path(name).suffix.lower()}"
        )
    return None


def validate_tracked_files(files: list[TrackedFile], expected_license: bytes) -> None:
    """Validate export paths and the required Apache-2.0 license."""
    file_by_path = {str(item.relative_path): item for item in files}
    require(len(file_by_path) == len(files), "distribution contains duplicate paths")
    for item in files:
        path = item.relative_path
        require(not path.is_absolute(), f"absolute export path is forbidden: {path}")
        require(".." not in path.parts, f"parent traversal is forbidden: {path}")
        require(
            path.name not in GENERATED_NAMES,
            f"canonical source must not own generated file: {path}",
        )
        reason = forbidden_reason(path)
        require(reason is None, f"unsafe tracked export file {path}: {reason}")

    license_file = file_by_path.get("LICENSE")
    if license_file is None:
        raise RuntimeError("distribution must contain a tracked LICENSE at its root")
    require(
        license_file.content == expected_license,
        "distribution LICENSE must exactly match the root Apache-2.0 LICENSE",
    )


def git_file_content(
    repository_root: Path, revision: str, path: PurePosixPath
) -> bytes:
    """Read one repository file from the selected source revision."""
    output = run_git(repository_root, ["show", f"{revision}:{path}"])
    require(isinstance(output, bytes), "Git file output must be bytes")
    return output


def revision_studio_version(repository_root: Path, revision: str) -> str:
    """Read the canonical Studio version from the selected source revision."""
    output = git_file_content(
        repository_root, revision, PurePosixPath("apps/studio/VERSION")
    )
    return output.decode("utf-8").strip()


def declared_compatible_sdk_version(
    distribution: Distribution,
    files: list[TrackedFile],
) -> str | None:
    """Read compatible SDK metadata from the distribution's committed source."""
    file_by_path = {str(item.relative_path): item.content for item in files}
    if distribution.name == "minimal":
        readme = file_by_path.get("README.md")
        if readme is None:
            raise RuntimeError("minimal distribution must contain README.md")
        match = re.search(
            rb"Applications that emit Junjo workflow telemetry should use Junjo `([^`]+)`",
            readme,
        )
        if match is None:
            raise RuntimeError(
                "minimal README must declare its compatible Junjo SDK version"
            )
        return match.group(1).decode("ascii")
    if distribution.name == "vm-caddy":
        requirements = file_by_path.get("junjo_app/requirements.txt")
        if requirements is None:
            raise RuntimeError("vm-caddy must contain junjo_app/requirements.txt")
        match = re.search(rb"(?m)^junjo==([^\s]+)$", requirements)
        if match is None:
            raise RuntimeError(
                "vm-caddy requirements must pin its compatible Junjo SDK version"
            )
        return match.group(1).decode("ascii")
    return None


def source_metadata(
    distribution: Distribution,
    source_repository: str,
    source_revision: str,
    studio_version: str,
    compatible_sdk_version: str | None,
) -> dict[str, str | int | None]:
    """Build deterministic machine-readable distribution provenance."""
    return {
        "schema_version": 1,
        "distribution": distribution.name,
        "source_repository": source_repository,
        "canonical_source_path": str(distribution.canonical_path),
        "source_revision": source_revision,
        "studio_version": studio_version,
        "compatible_sdk_version": compatible_sdk_version,
    }


def generated_notice(metadata: dict[str, str | int | None]) -> bytes:
    """Build the operator-facing canonical-source notice."""
    sdk_version = metadata["compatible_sdk_version"] or "not declared"
    content = f"""# Generated Junjo AI Studio distribution

This repository or archive is generated from the canonical Junjo platform
monorepo. Do not edit this distribution as a separate source of truth.

- Source repository: {metadata["source_repository"]}
- Canonical source path: `{metadata["canonical_source_path"]}`
- Source commit: `{metadata["source_revision"]}`
- Studio version: `{metadata["studio_version"]}`
- Compatible Junjo Python SDK version: `{sdk_version}`

Propose source changes in the canonical monorepo. A validated Studio release
publishes this distribution one way from that source.
"""
    return content.encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    """Return the lowercase SHA-256 digest for bytes."""
    return hashlib.sha256(content).hexdigest()


def write_export_files(export_root: Path, files: list[TrackedFile]) -> None:
    """Write canonical Git blobs with deterministic regular-file permissions."""
    for item in files:
        destination = export_root.joinpath(*item.relative_path.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(item.content)
        destination.chmod(item.mode)


def inventory(
    export_root: Path,
    file_modes: dict[str, int],
) -> list[dict[str, str | int]]:
    """Create the stable inventory used to calculate the export tree digest."""
    entries: list[dict[str, str | int]] = []
    for path in sorted(export_root.rglob("*")):
        if path.is_dir():
            continue
        require(
            path.is_file() and not path.is_symlink(),
            f"export contains a non-regular file: {path}",
        )
        relative_path = path.relative_to(export_root).as_posix()
        require(
            relative_path != MANIFEST,
            f"{MANIFEST} must not exist before inventory generation",
        )
        require(
            relative_path in file_modes, f"export mode is undefined: {relative_path}"
        )
        content = path.read_bytes()
        entries.append(
            {
                "path": relative_path,
                "size": len(content),
                "mode": f"{file_modes[relative_path]:04o}",
                "sha256": sha256_bytes(content),
            }
        )
    require(
        {str(entry["path"]) for entry in entries} == set(file_modes),
        "export file modes must exactly match the inventory",
    )
    return entries


def tree_digest(entries: list[dict[str, str | int]]) -> str:
    """Calculate the deterministic digest of an ordered export inventory."""
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(encoded)


def write_manifest(
    export_root: Path,
    metadata: dict[str, str | int | None],
    entries: list[dict[str, str | int]],
) -> dict[str, object]:
    """Write the deterministic inventory and provenance manifest."""
    manifest: dict[str, object] = {
        "schema_version": 1,
        "source": metadata,
        "tree_sha256": tree_digest(entries),
        "inventory": entries,
    }
    content = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    path = export_root / MANIFEST
    path.write_text(content, encoding="utf-8")
    path.chmod(0o644)
    return manifest


def archive_paths(export_root: Path) -> list[Path]:
    """Return every export directory and file in stable POSIX path order."""
    return sorted(
        export_root.rglob("*"),
        key=lambda path: path.relative_to(export_root).as_posix(),
    )


def write_deterministic_archive(
    export_root: Path,
    archive: Path,
    archive_root_name: str,
    file_modes: dict[str, int],
) -> None:
    """Create a gzip-compressed tar archive without timestamps or host ownership."""
    with archive.open("wb") as raw_file:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw_file, mtime=0
        ) as gzip_file:
            with tarfile.open(
                fileobj=gzip_file, mode="w", format=tarfile.GNU_FORMAT
            ) as tar:
                root_info = tarfile.TarInfo(archive_root_name)
                root_info.type = tarfile.DIRTYPE
                root_info.mode = 0o755
                root_info.mtime = 0
                root_info.uid = 0
                root_info.gid = 0
                root_info.uname = ""
                root_info.gname = ""
                tar.addfile(root_info)

                for path in archive_paths(export_root):
                    relative = path.relative_to(export_root).as_posix()
                    archive_path = f"{archive_root_name}/{relative}"
                    info = tarfile.TarInfo(archive_path)
                    info.mtime = 0
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    if path.is_dir():
                        info.type = tarfile.DIRTYPE
                        info.mode = 0o755
                        tar.addfile(info)
                        continue
                    require(
                        path.is_file() and not path.is_symlink(),
                        f"cannot archive non-regular file: {path}",
                    )
                    content = path.read_bytes()
                    info.type = tarfile.REGTYPE
                    require(
                        relative in file_modes, f"archive mode is undefined: {relative}"
                    )
                    info.mode = file_modes[relative]
                    info.size = len(content)
                    tar.addfile(info, io.BytesIO(content))


def validate_staged_export(
    export_root: Path,
    distribution: Distribution,
    studio_version: str,
) -> None:
    """Validate exported Compose and setup content outside the monorepo tree."""
    validator = Path(__file__).with_name("validate_studio_deployments.py")
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(validator),
                "--distribution",
                distribution.name,
                "--distribution-root",
                str(export_root),
                "--studio-version",
                studio_version,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        output = "\n".join(
            part.strip() for part in (error.stdout, error.stderr) if part
        )
        raise RuntimeError(
            f"staged distribution validation failed:\n{output}"
        ) from error
    require(
        "Validated exported Studio deployment" in result.stdout,
        "staged distribution validator did not report success",
    )


def build_export(
    *,
    repository_root: Path,
    distribution: Distribution,
    source_repository: str,
    source_revision: str,
    studio_version: str,
    compatible_sdk_version: str | None,
    output_directory: Path,
    archive: Path,
) -> dict[str, object]:
    """Build one fresh distribution directory and matching deterministic archive."""
    repository_root = repository_root.resolve()
    output_directory = output_directory.resolve()
    archive = archive.resolve()
    validate_metadata_value("source repository", source_repository)
    require(
        source_repository == CANONICAL_SOURCE_REPOSITORY,
        f"source repository must be {CANONICAL_SOURCE_REPOSITORY}",
    )
    validate_metadata_value("Studio version", studio_version)
    require(
        VERSION_PATTERN.fullmatch(studio_version) is not None,
        "Studio version must be semantic",
    )
    require(
        compatible_sdk_version is not None
        or not distribution.requires_compatible_sdk_version,
        f"{distribution.name} requires --compatible-sdk-version metadata",
    )
    if compatible_sdk_version is not None:
        validate_metadata_value("compatible SDK version", compatible_sdk_version)
        require(
            VERSION_PATTERN.fullmatch(compatible_sdk_version) is not None,
            "compatible SDK version must be semantic",
        )
    require(
        not output_directory.exists(),
        f"output directory already exists: {output_directory}",
    )
    require(not archive.exists(), f"archive already exists: {archive}")
    require(output_directory != archive, "output directory and archive must differ")
    require(
        not archive.is_relative_to(output_directory),
        "archive must not be created inside the export directory",
    )

    commit = resolve_revision(repository_root, source_revision)
    committed_version = revision_studio_version(repository_root, commit)
    require(
        committed_version == studio_version,
        f"requested Studio {studio_version} does not match {commit}:apps/studio/VERSION "
        f"({committed_version})",
    )
    files = tracked_files_at_revision(repository_root, commit, distribution)
    root_license = git_file_content(repository_root, commit, PurePosixPath("LICENSE"))
    validate_tracked_files(files, root_license)
    declared_sdk_version = declared_compatible_sdk_version(distribution, files)
    require(
        compatible_sdk_version == declared_sdk_version,
        f"requested compatible SDK {compatible_sdk_version} does not match committed "
        f"{distribution.name} metadata ({declared_sdk_version})",
    )
    metadata = source_metadata(
        distribution,
        source_repository,
        commit,
        studio_version,
        compatible_sdk_version,
    )

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary_parent = output_directory.parent
    with (
        tempfile.TemporaryDirectory(
            prefix="junjo-distribution-export-",
            dir=temporary_parent,
        ) as temporary,
        tempfile.TemporaryDirectory(
            prefix="junjo-distribution-archive-",
            dir=archive.parent,
        ) as temporary_archive,
    ):
        temporary_root = Path(temporary)
        staged_export = temporary_root / "export"
        staged_archive = Path(temporary_archive) / "distribution.tar.gz"
        staged_export.mkdir()
        staged_export.chmod(0o755)
        write_export_files(staged_export, files)
        file_modes = {str(item.relative_path): item.mode for item in files}
        notice = staged_export / GENERATED_NOTICE
        notice.write_bytes(generated_notice(metadata))
        notice.chmod(0o644)
        file_modes[GENERATED_NOTICE] = 0o644
        for directory in (path for path in staged_export.rglob("*") if path.is_dir()):
            directory.chmod(0o755)
        validate_staged_export(staged_export, distribution, studio_version)
        entries = inventory(staged_export, file_modes)
        manifest = write_manifest(staged_export, metadata, entries)
        archive_file_modes = {**file_modes, MANIFEST: 0o644}
        archive_root_name = f"{distribution.archive_name_prefix}-{studio_version}"
        write_deterministic_archive(
            staged_export,
            staged_archive,
            archive_root_name,
            archive_file_modes,
        )
        archive_sha256 = sha256_bytes(staged_archive.read_bytes())

        os.replace(staged_export, output_directory)
        try:
            os.replace(staged_archive, archive)
        except BaseException:
            if output_directory.exists():
                shutil.rmtree(output_directory)
            raise

    report: dict[str, object] = {
        "distribution": distribution.name,
        "output_directory": str(output_directory),
        "archive": str(archive),
        "archive_sha256": archive_sha256,
        "tree_sha256": manifest["tree_sha256"],
        "inventory": manifest["inventory"],
        "source": metadata,
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    """Build the distribution export command-line parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Export committed Studio deployment files with deterministic provenance, "
            "inventory, and archive metadata."
        )
    )
    parser.add_argument("--distribution", choices=sorted(DISTRIBUTIONS), required=True)
    parser.add_argument(
        "--source-repository", required=True, help="Canonical source repository URL."
    )
    parser.add_argument(
        "--source-revision", required=True, help="Git commit or revision to export."
    )
    parser.add_argument(
        "--studio-version",
        required=True,
        help="Studio semantic version for this export.",
    )
    parser.add_argument(
        "--compatible-sdk-version",
        help="Compatible Junjo Python SDK semantic version, when the distribution declares one.",
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=DEFAULT_REPOSITORY_ROOT,
        help="Junjo repository root (default: inferred from this script).",
    )
    return parser


def main() -> int:
    """Build one export and print its machine-readable report."""
    args = build_parser().parse_args()
    report = build_export(
        repository_root=args.repository_root,
        distribution=DISTRIBUTIONS[args.distribution],
        source_repository=args.source_repository,
        source_revision=args.source_revision,
        studio_version=args.studio_version,
        compatible_sdk_version=args.compatible_sdk_version,
        output_directory=args.output_directory,
        archive=args.archive,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
