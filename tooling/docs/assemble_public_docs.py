#!/usr/bin/env python3
"""Assemble source-owned documentation into the Starlight staging tree."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WEBSITE_ROOT = REPOSITORY_ROOT / "apps/website"
CONTENT_OUTPUT = WEBSITE_ROOT / "src/content/docs/generated"
ASSET_OUTPUT = WEBSITE_ROOT / "public/docs-assets/generated/python"
MANIFEST_OUTPUT = WEBSITE_ROOT / "public/docs-manifests/generated/python"
ASSEMBLY_RECORD = WEBSITE_ROOT / ".docs-assembly/manifest.json"
LEGACY_SITE_OUTPUT = WEBSITE_ROOT / ".docs-assembly/python-api-site"
LEGACY_SITE_SOURCE = WEBSITE_ROOT / "legacy-python-api"
PYTHON_ROOT = REPOSITORY_ROOT / "sdks/python"
STABLE_RELEASES = REPOSITORY_ROOT / "tooling/docs/stable-releases.json"
RELEASE_SNAPSHOTS = REPOSITORY_ROOT / "tooling/docs/release-snapshots"
DOCUMENTATION_CHANNEL = os.environ.get("JUNJO_DOCS_CHANNEL", "next")


@dataclass(frozen=True)
class ComponentSource:
    name: str
    version: str
    release_tag: str
    release_revision: str
    documentation_revision: str
    content_format: str
    root: Path


@dataclass(frozen=True)
class DocumentationSources:
    python: ComponentSource
    studio: ComponentSource


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


def git_output(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def resolve_git_ref(reference: str) -> str:
    try:
        return git_output("rev-parse", "--verify", f"{reference}^{{commit}}")
    except subprocess.CalledProcessError:
        if reference.startswith(("sdk-python-v", "studio-v", "docs-release-")):
            subprocess.run(
                [
                    "git",
                    "fetch",
                    "--force",
                    "origin",
                    f"refs/tags/{reference}:refs/tags/{reference}",
                ],
                cwd=REPOSITORY_ROOT,
                check=True,
            )
        else:
            subprocess.run(
                ["git", "fetch", "--no-tags", "origin", reference],
                cwd=REPOSITORY_ROOT,
                check=True,
            )
        return git_output("rev-parse", "--verify", f"{reference}^{{commit}}")


def python_version(root: Path) -> str:
    with (root / "sdks/python/pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def studio_version(root: Path) -> str:
    payload = json.loads(
        (root / "apps/studio/frontend/package.json").read_text(encoding="utf-8")
    )
    return str(payload["version"])


def load_stable_manifest() -> dict[str, object]:
    manifest = json.loads(STABLE_RELEASES.read_text(encoding="utf-8"))
    if manifest.get("version") != 1:
        raise ValueError("unsupported stable documentation manifest version")
    return manifest


def component_entry_fields(name: str, entry: object) -> tuple[str, str, str, str, bool]:
    if not isinstance(entry, dict):
        raise ValueError(f"stable documentation manifest has no {name} entry")
    required = {
        "version",
        "release_tag",
        "documentation_ref",
        "content_format",
        "migration_snapshot",
    }
    if set(entry) != required:
        raise ValueError(f"stable {name} entry must contain exactly {sorted(required)}")
    version = entry["version"]
    release_tag = entry["release_tag"]
    documentation_ref = entry["documentation_ref"]
    content_format = entry["content_format"]
    migration_snapshot = entry["migration_snapshot"]
    if not all(
        isinstance(value, str)
        for value in (version, release_tag, documentation_ref, content_format)
    ):
        raise ValueError(f"stable {name} string fields are invalid")
    if not isinstance(migration_snapshot, bool):
        raise ValueError(f"stable {name} migration_snapshot must be boolean")

    expected_tag = (
        f"sdk-python-v{version}" if name == "python" else f"studio-v{version}"
    )
    if release_tag != expected_tag:
        raise ValueError(
            f"stable {name} release tag must be {expected_tag}, received {release_tag}"
        )
    allowed_formats = {"owned-markdown"}
    if name == "python":
        allowed_formats.add("legacy-rst")
    if content_format not in allowed_formats:
        raise ValueError(f"unsupported stable {name} content format: {content_format}")
    return version, release_tag, documentation_ref, content_format, migration_snapshot


def validate_component_entry(
    name: str, entry: object, checkout_root: Path
) -> ComponentSource:
    version, release_tag, documentation_ref, content_format, migration_snapshot = (
        component_entry_fields(name, entry)
    )

    release_revision = resolve_git_ref(release_tag)
    documentation_revision = resolve_git_ref(documentation_ref)
    if not migration_snapshot and documentation_revision != release_revision:
        raise ValueError(
            f"stable {name} documentation must come from its exact release tag"
        )
    if migration_snapshot:
        git_output(
            "merge-base", "--is-ancestor", release_revision, documentation_revision
        )

    checkout = checkout_root / name
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(checkout), documentation_revision],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    try:
        actual_version = (
            python_version(checkout) if name == "python" else studio_version(checkout)
        )
        if actual_version != version:
            raise ValueError(
                f"stable {name} documentation revision has version {actual_version}; expected {version}"
            )
    except Exception:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(checkout)],
            cwd=REPOSITORY_ROOT,
            check=False,
        )
        raise
    return ComponentSource(
        name=name,
        version=version,
        release_tag=release_tag,
        release_revision=release_revision,
        documentation_revision=documentation_revision,
        content_format=content_format,
        root=checkout,
    )


@contextlib.contextmanager
def stable_documentation_sources(checkout_root: Path) -> Iterator[DocumentationSources]:
    manifest = load_stable_manifest()
    created: list[Path] = []
    try:
        python = validate_component_entry(
            "python", manifest.get("python"), checkout_root
        )
        created.append(python.root)
        studio = validate_component_entry(
            "studio", manifest.get("studio"), checkout_root
        )
        created.append(studio.root)
        yield DocumentationSources(python=python, studio=studio)
    finally:
        for checkout in reversed(created):
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(checkout)],
                cwd=REPOSITORY_ROOT,
                check=False,
            )


def run_python_api_export(
    output: Path,
    *,
    sdk_root: Path = PYTHON_ROOT,
    surface: Path | None = None,
    revision: str | None = None,
) -> None:
    command = [
        "uv",
        "run",
        "--project",
        str(PYTHON_ROOT),
        "python",
        str(PYTHON_ROOT / "docs/export_api.py"),
        "generate",
        "--clean",
        "--output",
        str(output),
        "--sdk-root",
        str(sdk_root),
        "--channel",
        DOCUMENTATION_CHANNEL,
    ]
    if surface is not None:
        command.extend(("--surface", str(surface)))
    if revision is not None:
        command.extend(("--revision", revision))
    subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=True,
    )


def export_release_rst(source: ComponentSource, output: Path) -> None:
    subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(REPOSITORY_ROOT / "tooling/docs"),
            "python",
            str(REPOSITORY_ROOT / "tooling/docs/convert_legacy_rst.py"),
            "--source-docs",
            str(source.root / "sdks/python/docs"),
            "--output",
            str(output),
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )


def documentation_route(path: Path, content: Path) -> str:
    relative = path.relative_to(content).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "index":
        parts.pop()
    return "/" + "/".join(parts) + "/"


def build_assembly(root: Path, sources: DocumentationSources | None = None) -> None:
    content = root / "content"
    assets = root / "assets"
    manifests = root / "manifests"
    record_path = root / "assembly-manifest.json"
    api_export = root / "python-api"

    if sources is None:
        python_docs_root = REPOSITORY_ROOT / "sdks/python/docs"
        studio_root = REPOSITORY_ROOT
        copy_tree_without_overwrite(python_docs_root / "content", content)
        python_surface = python_docs_root / "api-public-surface.json"
        python_revision = git_output("rev-parse", "HEAD")
    else:
        python_docs_root = sources.python.root / "sdks/python/docs"
        studio_root = sources.studio.root
        if sources.python.content_format == "owned-markdown":
            copy_tree_without_overwrite(python_docs_root / "content", content)
            python_surface = python_docs_root / "api-public-surface.json"
        else:
            export_release_rst(sources.python, content)
            python_surface = (
                RELEASE_SNAPSHOTS
                / "python"
                / sources.python.version
                / "api-public-surface.json"
            )
            if not python_surface.is_file():
                raise FileNotFoundError(
                    "missing immutable Python API surface for legacy release "
                    f"{sources.python.version}: {python_surface}"
                )
        python_revision = sources.python.documentation_revision

    copy_tree_without_overwrite(studio_root / "apps/studio/docs/public", content)
    run_python_api_export(
        api_export,
        sdk_root=python_docs_root.parent,
        surface=python_surface,
        revision=python_revision,
    )
    copy_tree_without_overwrite(api_export / "docs", content / "docs")
    copy_tree_without_overwrite(python_docs_root / "_static", assets)

    manifests.mkdir(parents=True, exist_ok=True)
    shutil.copy2(api_export / "api-manifest.json", manifests / "api-manifest.json")
    shutil.copy2(
        python_surface,
        manifests / "api-public-surface.json",
    )
    shutil.copy2(
        REPOSITORY_ROOT / "tooling/docs/content-migration.json",
        manifests / "content-migration.json",
    )
    shutil.copy2(
        REPOSITORY_ROOT / "tooling/docs/legacy-routes.json",
        manifests / "legacy-routes.json",
    )

    copy_tree_without_overwrite(LEGACY_SITE_SOURCE, root / "python-api-site")

    api_manifest = json.loads(
        (manifests / "api-manifest.json").read_text(encoding="utf-8")
    )
    published_routes = sorted(
        documentation_route(path, content)
        for path in content.rglob("*.md")
        if path.is_file()
    )
    python_publication: dict[str, object] = {
        "version": api_manifest["sdk_version"],
        "source_revision": api_manifest["source_revision"],
    }
    publication_manifest: dict[str, object] = {
        "version": 1,
        "documentation_channel": DOCUMENTATION_CHANNEL,
        "routes": published_routes,
        "python": python_publication,
    }
    if sources is not None:
        python_publication.update(
            {
                "release_tag": sources.python.release_tag,
                "release_revision": sources.python.release_revision,
                "content_format": sources.python.content_format,
            }
        )
        publication_manifest["studio"] = {
            "version": sources.studio.version,
            "release_tag": sources.studio.release_tag,
            "release_revision": sources.studio.release_revision,
            "source_revision": sources.studio.documentation_revision,
            "content_format": sources.studio.content_format,
        }
    (manifests / "publication-manifest.json").write_text(
        json.dumps(publication_manifest, indent=2) + "\n", encoding="utf-8"
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
        "stable_release_manifest_hash": (
            sha256_file(STABLE_RELEASES) if sources is not None else None
        ),
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
        if DOCUMENTATION_CHANNEL == "stable":
            with stable_documentation_sources(
                temporary / "source-checkouts"
            ) as sources:
                build_assembly(temporary, sources)
                return finish_assembly(temporary, args.write)
        if DOCUMENTATION_CHANNEL != "next":
            raise ValueError(
                f"JUNJO_DOCS_CHANNEL must be next or stable, received {DOCUMENTATION_CHANNEL}"
            )
        build_assembly(temporary)
        return finish_assembly(temporary, args.write)


def finish_assembly(temporary: Path, write: bool) -> int:
    if write:
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
