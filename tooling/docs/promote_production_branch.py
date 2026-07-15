#!/usr/bin/env python3
"""Advance the Cloudflare production source branch to a published release."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_BRANCH = "docs-production"
RELEASE_TAG = re.compile(
    r"(?:sdk-python-v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?|"
    r"studio-v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?|"
    r"docs-release-\d{8}\.\d+)"
)


def run(*arguments: str, capture: bool = False) -> str:
    result = subprocess.run(
        list(arguments),
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=capture,
        text=True,
    )
    return result.stdout.strip() if capture else ""


def git_output(*arguments: str) -> str:
    return run("git", *arguments, capture=True)


def require_ancestor(ancestor: str, descendant: str, message: str) -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(message)


def published_release(repository: str, tag: str) -> dict[str, object]:
    payload = json.loads(
        run(
            "gh",
            "api",
            f"repos/{repository}/releases/tags/{tag}",
            capture=True,
        )
    )
    if payload.get("draft") is not False or not payload.get("published_at"):
        raise ValueError(f"GitHub release {tag} is not published")
    if payload.get("tag_name") != tag:
        raise ValueError(f"GitHub release lookup returned the wrong tag for {tag}")
    return payload


def promote(repository: str, tag: str, dry_run: bool) -> str:
    if RELEASE_TAG.fullmatch(tag) is None:
        raise ValueError(f"unsupported documentation release tag: {tag}")
    published_release(repository, tag)

    run(
        "git",
        "fetch",
        "--force",
        "origin",
        "master:refs/remotes/origin/master",
        f"{PRODUCTION_BRANCH}:refs/remotes/origin/{PRODUCTION_BRANCH}",
        f"refs/tags/{tag}:refs/tags/{tag}",
    )
    target = git_output("rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
    current = git_output(
        "rev-parse", "--verify", f"refs/remotes/origin/{PRODUCTION_BRANCH}^{{commit}}"
    )
    require_ancestor(
        target,
        "refs/remotes/origin/master",
        f"release {tag} at {target} is not reachable from origin/master",
    )
    if current == target:
        print(f"{PRODUCTION_BRANCH} already points to published release {tag} ({target}).")
        return target
    require_ancestor(
        current,
        target,
        f"refusing to move {PRODUCTION_BRANCH} non-fast-forward from {current} to {target}",
    )
    if dry_run:
        print(f"Validated promotion of {PRODUCTION_BRANCH} from {current} to {target}.")
        return target

    run(
        "gh",
        "api",
        "--method",
        "PATCH",
        f"repos/{repository}/git/refs/heads/{PRODUCTION_BRANCH}",
        "-f",
        f"sha={target}",
        "-F",
        "force=false",
    )
    promoted = run(
        "gh",
        "api",
        f"repos/{repository}/git/ref/heads/{PRODUCTION_BRANCH}",
        "--jq",
        ".object.sha",
        capture=True,
    )
    if promoted != target:
        raise ValueError(
            f"{PRODUCTION_BRANCH} resolved to {promoted} after promotion; expected {target}"
        )
    print(f"Promoted {PRODUCTION_BRANCH} to published release {tag} ({target}).")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.repository:
        parser.error("--repository or GITHUB_REPOSITORY is required")
    promote(args.repository, args.release_tag, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
