#!/usr/bin/env python3
"""Validate that a release publishes the intended stable documentation set."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from collections.abc import Callable
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
STABLE_RELEASES = REPOSITORY_ROOT / "tooling/docs/stable-releases.json"
DOCS_RELEASE = re.compile(r"docs-release-\d{8}\.\d+")
GITHUB_RELEASE_API = "https://api.github.com/repos/mdrideout/junjo/releases/tags/{tag}"
PYPI_RELEASE_API = "https://pypi.org/pypi/junjo/{version}/json"


def _load_json_url(url: str) -> dict[str, object]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "junjo-release-validator",
    }
    if url.startswith("https://api.github.com/") and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    request = urllib.request.Request(
        url,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError(f"release evidence endpoint returned non-object JSON: {url}")
    return payload


def validate_published_selection(
    manifest: dict[str, object],
    load_json_url: Callable[[str], dict[str, object]] = _load_json_url,
) -> None:
    """Require docs-only promotion to reference artifacts that actually shipped."""
    for component in ("python", "studio"):
        entry = manifest.get(component)
        if not isinstance(entry, dict):
            raise ValueError(f"stable documentation manifest has no {component} entry")
        tag = entry.get("release_tag")
        version = entry.get("version")
        if not isinstance(tag, str) or not isinstance(version, str):
            raise ValueError(f"stable documentation manifest has invalid {component} identity")

        release = load_json_url(GITHUB_RELEASE_API.format(tag=tag))
        if release.get("draft") is not False or not release.get("published_at"):
            raise ValueError(f"stable {component} release {tag} is not published")

        if component == "studio":
            assets = release.get("assets")
            asset_names = (
                {asset.get("name") for asset in assets if isinstance(asset, dict)}
                if isinstance(assets, list)
                else set()
            )
            if "RELEASE_EVIDENCE.json" not in asset_names:
                raise ValueError(f"stable Studio release {tag} has no RELEASE_EVIDENCE.json")
        else:
            pypi = load_json_url(PYPI_RELEASE_API.format(version=version))
            info = pypi.get("info")
            urls = pypi.get("urls")
            if not isinstance(info, dict) or info.get("version") != version or not urls:
                raise ValueError(f"junjo {version} is not installable from PyPI")


def validate_release_tag(
    tag: str,
    manifest: dict[str, object],
    publication_validator: Callable[[dict[str, object]], None] = validate_published_selection,
) -> None:
    if tag.startswith("sdk-python-v"):
        component = "python"
    elif tag.startswith("studio-v"):
        component = "studio"
    elif DOCS_RELEASE.fullmatch(tag):
        publication_validator(manifest)
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
