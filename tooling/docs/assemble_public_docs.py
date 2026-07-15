#!/usr/bin/env python3
"""Assemble source-owned documentation into the Starlight staging tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WEBSITE_ROOT = REPOSITORY_ROOT / "apps/website"
CONTENT_OUTPUT = WEBSITE_ROOT / "src/content/docs/generated"
ASSET_OUTPUT = WEBSITE_ROOT / "public/docs-assets/generated/python"
MANIFEST_OUTPUT = WEBSITE_ROOT / "public/docs-manifests/generated/python"
ASSEMBLY_RECORD = WEBSITE_ROOT / ".docs-assembly/manifest.json"
LEGACY_SITE_OUTPUT = WEBSITE_ROOT / ".docs-assembly/python-api-site"
PYTHON_ROOT = REPOSITORY_ROOT / "sdks/python"
DOCUMENTATION_CHANNEL = os.environ.get("JUNJO_DOCS_CHANNEL", "next")
LEGACY_REDIRECT_TARGET = "https://junjo.ai/docs/python/"


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def copy_tree_without_overwrite(source: Path, destination: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    for source_path in sorted(source.rglob("*")):
        if not source_path.is_file():
            continue
        relative = source_path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != source_path.read_bytes():
            raise ValueError(f"documentation assembly collision at {relative}")
        shutil.copy2(source_path, target)


def run_python_api_export(output: Path) -> None:
    subprocess.run(
        [
            "uv",
            "run",
            "--frozen",
            "--extra",
            "dev",
            "python",
            "docs/export_api.py",
            "generate",
            "--clean",
            "--output",
            str(output),
            "--channel",
            DOCUMENTATION_CHANNEL,
        ],
        cwd=PYTHON_ROOT,
        check=True,
    )


def build_assembly(root: Path) -> None:
    content = root / "content"
    assets = root / "assets"
    manifests = root / "manifests"
    record_path = root / "assembly-manifest.json"
    api_export = root / "python-api"

    copy_tree_without_overwrite(REPOSITORY_ROOT / "sdks/python/docs/content", content)
    copy_tree_without_overwrite(REPOSITORY_ROOT / "apps/studio/docs/public", content)
    run_python_api_export(api_export)
    copy_tree_without_overwrite(api_export / "docs", content / "docs")
    copy_tree_without_overwrite(REPOSITORY_ROOT / "sdks/python/docs/_static", assets)

    manifests.mkdir(parents=True, exist_ok=True)
    shutil.copy2(api_export / "api-manifest.json", manifests / "api-manifest.json")
    shutil.copy2(
        REPOSITORY_ROOT / "sdks/python/docs/api-sphinx-baseline.json",
        manifests / "sphinx-api-baseline.json",
    )
    shutil.copy2(
        REPOSITORY_ROOT / "tooling/docs/content-migration.json",
        manifests / "content-migration.json",
    )
    shutil.copy2(
        REPOSITORY_ROOT / "tooling/docs/legacy-routes.json",
        manifests / "legacy-routes.json",
    )

    legacy_site = root / "python-api-site"
    legacy_site.mkdir(parents=True)
    (legacy_site / "_redirects").write_text(
        "# The Python Sphinx site is retired. All legacy requests enter the unified docs here.\n"
        f"/* {LEGACY_REDIRECT_TARGET} 301\n",
        encoding="utf-8",
    )

    api_manifest = json.loads(
        (manifests / "api-manifest.json").read_text(encoding="utf-8")
    )
    legacy_api_map: dict[str, str] = {}
    for symbol in api_manifest["symbols"]:
        anchor = symbol["legacy_anchor"]
        if not anchor:
            continue
        target = f"{symbol['target_route']}#{symbol['target_anchor']}"
        previous = legacy_api_map.setdefault(anchor, target)
        if previous != target:
            raise ValueError(f"legacy API anchor {anchor} has conflicting targets")
    (manifests / "legacy-api-map.json").write_text(
        json.dumps({"version": 1, "symbols": legacy_api_map}, indent=2) + "\n",
        encoding="utf-8",
    )

    files: list[dict[str, str]] = []
    for category, directory in (
        ("content", content),
        ("asset", assets),
        ("manifest", manifests),
    ):
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                files.append(
                    {
                        "category": category,
                        "path": str(path.relative_to(root)),
                        "hash": sha256_file(path),
                    }
                )
    files.append(
        {
            "category": "compatibility",
            "path": "python-api-site/_redirects",
            "hash": sha256_file(root / "python-api-site/_redirects"),
        }
    )
    record = {
        "version": 1,
        "python_sdk_version": api_manifest["sdk_version"],
        "python_source_revision": api_manifest["source_revision"],
        "documentation_channel": api_manifest["channel"],
        "files": files,
    }
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def replace_output(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)


def write_assembly(temporary: Path) -> None:
    replace_output(temporary / "content", CONTENT_OUTPUT)
    replace_output(temporary / "assets", ASSET_OUTPUT)
    replace_output(temporary / "manifests", MANIFEST_OUTPUT)
    ASSEMBLY_RECORD.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(temporary / "assembly-manifest.json", ASSEMBLY_RECORD)
    replace_output(temporary / "python-api-site", LEGACY_SITE_OUTPUT)


def directory_files(root: Path) -> dict[Path, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def compare_directory(expected: Path, actual: Path, label: str) -> list[str]:
    expected_files = directory_files(expected)
    actual_files = directory_files(actual)
    failures: list[str] = []
    missing = sorted(expected_files.keys() - actual_files.keys())
    extra = sorted(actual_files.keys() - expected_files.keys())
    stale = sorted(
        path
        for path in expected_files.keys() & actual_files.keys()
        if expected_files[path] != actual_files[path]
    )
    failures.extend(f"{label}: missing {path}" for path in missing)
    failures.extend(f"{label}: unexpected {path}" for path in extra)
    failures.extend(f"{label}: stale {path}" for path in stale)
    return failures


def check_assembly(temporary: Path) -> int:
    failures = [
        *compare_directory(temporary / "content", CONTENT_OUTPUT, "content"),
        *compare_directory(temporary / "assets", ASSET_OUTPUT, "assets"),
        *compare_directory(temporary / "manifests", MANIFEST_OUTPUT, "manifests"),
    ]
    expected_record = (temporary / "assembly-manifest.json").read_bytes()
    if not ASSEMBLY_RECORD.exists():
        failures.append("assembly record is missing")
    elif ASSEMBLY_RECORD.read_bytes() != expected_record:
        failures.append("assembly record is stale")
    failures.extend(
        compare_directory(
            temporary / "python-api-site",
            LEGACY_SITE_OUTPUT,
            "legacy-domain redirect site",
        )
    )
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    record = json.loads(expected_record)
    print(
        f"Validated {len(record['files'])} assembled documentation files for Python SDK {record['python_sdk_version']}."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="junjo-docs-assembly-") as directory:
        temporary = Path(directory)
        build_assembly(temporary)
        if args.write:
            write_assembly(temporary)
            record = json.loads(
                (temporary / "assembly-manifest.json").read_text(encoding="utf-8")
            )
            print(
                f"Assembled {len(record['files'])} documentation files into Starlight staging."
            )
            return 0
        return check_assembly(temporary)


if __name__ == "__main__":
    raise SystemExit(main())
