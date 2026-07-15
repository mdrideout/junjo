#!/usr/bin/env python3
"""Validate that a release publishes the intended stable documentation set."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
STABLE_RELEASES = REPOSITORY_ROOT / "tooling/docs/stable-releases.json"
DOCS_RELEASE = re.compile(r"docs-release-\d{8}\.\d+")


def validate_release_tag(tag: str, manifest: dict[str, object]) -> None:
    if tag.startswith("sdk-python-v"):
        component = "python"
    elif tag.startswith("studio-v"):
        component = "studio"
    elif DOCS_RELEASE.fullmatch(tag):
        return
    else:
        raise ValueError(f"unsupported documentation release tag: {tag}")

    entry = manifest.get(component)
    if not isinstance(entry, dict) or entry.get("release_tag") != tag:
        selected = entry.get("release_tag") if isinstance(entry, dict) else None
        raise ValueError(
            f"{component} release {tag} cannot publish documentation selected for {selected}; "
            "update tooling/docs/stable-releases.json in the release commit"
        )
    if entry.get("migration_snapshot") is not False:
        raise ValueError(
            f"new {component} release {tag} must retire its migration snapshot"
        )
    if entry.get("documentation_ref") != tag:
        raise ValueError(
            f"new {component} release {tag} must document its exact release tag"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-tag", required=True)
    args = parser.parse_args()
    manifest = json.loads(STABLE_RELEASES.read_text(encoding="utf-8"))
    if manifest.get("version") != 1:
        raise ValueError("unsupported stable documentation manifest version")
    validate_release_tag(args.release_tag, manifest)
    print(f"Validated stable documentation selection for {args.release_tag}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
