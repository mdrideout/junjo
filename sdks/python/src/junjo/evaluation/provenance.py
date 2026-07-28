"""Clean committed source-revision provenance for evaluation runs."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

SourceRevision = Callable[[], str]


class DirtySourceTreeError(RuntimeError):
    """The evaluated checkout is dirty or its Git revision cannot be proven."""


def clean_source_revision(repository: Path | None = None) -> str:
    """Return ``HEAD`` only when the complete containing Git worktree is clean.

    :param repository: File or directory inside the application worktree.
        Defaults to the caller's current working directory.
    :returns: The clean 40- or 64-character lowercase Git object ID.
    :raises DirtySourceTreeError: If Git inspection fails or tracked/untracked
        changes make the candidate revision untruthful.
    """

    working_directory = (repository or Path.cwd()).resolve()
    if working_directory.is_file():
        working_directory = working_directory.parent
    root = _git(working_directory, "rev-parse", "--show-toplevel")
    status = _git(
        Path(root),
        "status",
        "--porcelain",
        "--untracked-files=normal",
    )
    if status:
        raise DirtySourceTreeError("Evaluation requires a clean committed Git worktree.")
    return _git(Path(root), "rev-parse", "HEAD")


def _git(working_directory: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(working_directory), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise DirtySourceTreeError("Unable to inspect the application Git revision.") from error
    return completed.stdout.strip()
