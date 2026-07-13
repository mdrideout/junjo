#!/usr/bin/env python3
"""Publish and verify one generated Studio distribution repository."""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from validate_studio_release_policy import load_release_contract


def require(condition: bool, message: str) -> None:
    """Raise a clear publication error when an invariant is false."""
    if not condition:
        raise RuntimeError(message)


def run(command: list[str], *, cwd: Path | None = None) -> str:
    """Run a command without exposing authentication environment values."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError(f"required command is unavailable: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        output = "\n".join(
            part.strip() for part in (error.stdout, error.stderr) if part
        )
        message = f"command failed: {command[0]}"
        if output:
            message = f"{message}\n{output}"
        raise RuntimeError(message) from error
    return result.stdout.strip()


def remove_worktree_contents(worktree: Path) -> None:
    """Remove generated mirror content while preserving its Git directory."""
    for child in worktree.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def copy_export(export_directory: Path, worktree: Path) -> None:
    """Copy the complete generated export into the mirror worktree."""
    for child in export_directory.iterdir():
        destination = worktree / child.name
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)


def relative_files(root: Path) -> list[str]:
    """Return every regular file path except Git internals."""
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    )


def require_equal_trees(expected: Path, actual: Path) -> None:
    """Prove a fresh mirror clone exactly matches the generated export."""
    expected_files = relative_files(expected)
    actual_files = relative_files(actual)
    require(
        actual_files == expected_files,
        f"mirror inventory differs: expected {expected_files}, found {actual_files}",
    )
    for relative_path in expected_files:
        require(
            filecmp.cmp(
                expected / relative_path,
                actual / relative_path,
                shallow=False,
            ),
            f"mirror content differs: {relative_path}",
        )
        expected_mode = stat.S_IMODE((expected / relative_path).stat().st_mode)
        actual_mode = stat.S_IMODE((actual / relative_path).stat().st_mode)
        require(
            actual_mode == expected_mode,
            f"mirror mode differs: {relative_path}: "
            f"expected {expected_mode:o}, found {actual_mode:o}",
        )


def validate_mirror_destination(
    distribution: str, destination: dict[str, str]
) -> dict[str, str]:
    """Resolve one contract-owned mirror and prove its identity and default branch."""
    repository = destination["mirror_repository"]
    branch = destination["mirror_branch"]
    response = run(
        [
            "gh",
            "api",
            f"repos/{repository}",
            "--jq",
            "{full_name: .full_name, default_branch: .default_branch}",
        ]
    )
    try:
        resolved = json.loads(response)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"GitHub returned invalid mirror identity JSON for {distribution}"
        ) from error
    require(
        isinstance(resolved, dict),
        f"GitHub mirror identity for {distribution} must be an object",
    )
    require(
        resolved.get("full_name") == repository,
        "GitHub resolved a different mirror repository than the release contract",
    )
    require(
        resolved.get("default_branch") == branch,
        f"GitHub mirror default branch for {distribution} must be {branch}",
    )
    return {
        "distribution": distribution,
        "repository": repository,
        "branch": branch,
    }


def validate_mirror_destinations() -> dict[str, object]:
    """Validate every mirror destination together before any publication mutation."""
    require(bool(os.environ.get("GH_TOKEN")), "GH_TOKEN is required")
    contract = load_release_contract()
    distributions = contract["distributions"]
    destinations = [
        validate_mirror_destination(name, distributions[name])
        for name in ("minimal", "vm-caddy")
    ]
    return {"schema_version": 1, "destinations": destinations}


def publish(
    *,
    export_directory: Path,
    distribution: str,
    source_revision: str,
) -> dict[str, str | bool]:
    """Publish one contract-bound export and verify its exact remote tree."""
    require(
        export_directory.is_dir(), f"export directory is missing: {export_directory}"
    )
    require(
        re.fullmatch(r"[0-9a-f]{40}", source_revision) is not None,
        "source revision must be a full lowercase 40-character Git SHA",
    )
    contract = load_release_contract()
    distributions = contract["distributions"]
    require(
        distribution in distributions,
        f"distribution is not in the Studio release contract: {distribution}",
    )
    destination = distributions[distribution]
    repository = destination["mirror_repository"]
    branch = destination["mirror_branch"]
    canonical_source_path = destination["canonical_source_path"]
    require(isinstance(repository, str), "mirror repository must be a string")
    require(isinstance(branch, str), "mirror branch must be a string")
    require(
        isinstance(canonical_source_path, str),
        "canonical source path must be a string",
    )

    manifest_path = export_directory / "EXPORT_MANIFEST.json"
    require(manifest_path.is_file(), "export manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = manifest.get("source")
    require(isinstance(source, dict), "export manifest source must be an object")
    require(
        source.get("distribution") == distribution,
        "export distribution does not match publication distribution",
    )
    require(
        source.get("canonical_source_path") == canonical_source_path,
        "export canonical source path does not match the release contract",
    )
    require(
        source.get("source_revision") == source_revision,
        "export source revision does not match publication revision",
    )
    require(bool(os.environ.get("GH_TOKEN")), "GH_TOKEN is required")
    validate_mirror_destination(distribution, destination)
    run(["gh", "auth", "setup-git"])

    with tempfile.TemporaryDirectory(prefix="junjo-mirror-publish-") as temporary:
        temporary_root = Path(temporary)
        worktree = temporary_root / "worktree"
        verification = temporary_root / "verification"
        run(
            ["gh", "repo", "clone", repository, str(worktree), "--", "--branch", branch]
        )
        remove_worktree_contents(worktree)
        copy_export(export_directory, worktree)
        run(["git", "config", "user.name", "Junjo Release Automation"], cwd=worktree)
        run(
            ["git", "config", "user.email", "actions@users.noreply.github.com"],
            cwd=worktree,
        )
        run(["git", "add", "--all"], cwd=worktree)
        changed = bool(run(["git", "status", "--porcelain"], cwd=worktree))
        if changed:
            run(
                [
                    "git",
                    "commit",
                    "-m",
                    f"Publish generated distribution from {source_revision[:12]}",
                ],
                cwd=worktree,
            )
            run(["git", "push", "origin", f"HEAD:{branch}"], cwd=worktree)

        remote_commit = run(["git", "rev-parse", "HEAD"], cwd=worktree)
        run(
            [
                "gh",
                "repo",
                "clone",
                repository,
                str(verification),
                "--",
                "--branch",
                branch,
            ]
        )
        require_equal_trees(export_directory, verification)
        verified_commit = run(["git", "rev-parse", "HEAD"], cwd=verification)
        require(
            remote_commit == verified_commit,
            "fresh clone resolved a different mirror commit",
        )

    return {
        "distribution": distribution,
        "repository": repository,
        "branch": branch,
        "commit": remote_commit,
        "source_revision": source_revision,
        "changed": changed,
        "tree_sha256": str(manifest["tree_sha256"]),
    }


def main() -> None:
    """Validate destinations or publish one generated distribution."""
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "validate-destinations",
        help="Validate every contract-owned mirror before publication.",
    )
    publish_parser = commands.add_parser(
        "publish",
        help="Publish and verify one generated distribution.",
    )
    publish_parser.add_argument("--export-directory", type=Path, required=True)
    publish_parser.add_argument("--distribution", required=True)
    publish_parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    if args.command == "validate-destinations":
        report = validate_mirror_destinations()
    else:
        report = publish(
            export_directory=args.export_directory.resolve(),
            distribution=args.distribution,
            source_revision=args.source_revision,
        )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        raise SystemExit(f"error: {error}") from error
