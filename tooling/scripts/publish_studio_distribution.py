#!/usr/bin/env python3
"""Publish and verify one generated Studio distribution repository."""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path


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


def publish(
    *,
    export_directory: Path,
    repository: str,
    branch: str,
    source_revision: str,
) -> dict[str, str | bool]:
    """Publish a generated export and verify the remote default tree."""
    require(bool(os.environ.get("GH_TOKEN")), "GH_TOKEN is required")
    require(
        export_directory.is_dir(), f"export directory is missing: {export_directory}"
    )
    manifest_path = export_directory / "EXPORT_MANIFEST.json"
    require(manifest_path.is_file(), "export manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(
        manifest.get("source", {}).get("source_revision") == source_revision,
        "export source revision does not match publication revision",
    )
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
        "repository": repository,
        "branch": branch,
        "commit": remote_commit,
        "source_revision": source_revision,
        "changed": changed,
        "tree_sha256": str(manifest["tree_sha256"]),
    }


def main() -> None:
    """Publish one generated distribution and print non-secret evidence JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-directory", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--branch", default="master")
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    report = publish(
        export_directory=args.export_directory.resolve(),
        repository=args.repository,
        branch=args.branch,
        source_revision=args.source_revision,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        raise SystemExit(f"error: {error}") from error
