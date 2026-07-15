#!/usr/bin/env python3
"""Export the public Junjo Python API from Griffe to Starlight Markdown."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import tomllib
from dataclasses import dataclass
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Any

import griffe

SDK_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SDK_ROOT.parents[1]
DEFAULT_SURFACE = Path(__file__).with_name("api-public-surface.json")
API_PREFIX = "/docs/python/api"


@dataclass(frozen=True)
class ModuleSection:
    title: str
    module: str
    introduction: str = ""


MODULE_SECTIONS = (
    ModuleSection("Core API", "junjo"),
    ModuleSection(
        "Agent Definitions",
        "junjo.agent.definition",
        "The common definition and binding types are also available from `junjo`.",
    ),
    ModuleSection("Agent Model Drivers", "junjo.agent.model_driver"),
    ModuleSection("Agent Tools", "junjo.agent.tool"),
    ModuleSection("Agent Messages", "junjo.agent.messages"),
    ModuleSection("Agent Results", "junjo.agent.result"),
    ModuleSection("Agent State", "junjo.agent.state"),
    ModuleSection("Agent JSON", "junjo.agent.json"),
    ModuleSection("Agent Errors", "junjo.agent.errors"),
    ModuleSection(
        "Agent Testing",
        "junjo.agent.testing",
        "Deterministic scripted testing support is intentionally public at `junjo.agent.testing`.",
    ),
    ModuleSection("Hooks API", "junjo.hooks"),
    ModuleSection("Telemetry API", "junjo.telemetry.junjo_otel_exporter"),
)


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def json_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def slug_for_symbol(symbol: str) -> str:
    return "/".join(part.lower() for part in symbol.split("."))


def object_slug_for_symbol(symbol: str) -> str:
    slug = slug_for_symbol(symbol)
    module_slugs = {slug_for_symbol(section.module) for section in MODULE_SECTIONS}
    return f"{slug}/object" if slug in module_slugs else slug


def route_for_symbol(symbol: str) -> str:
    return f"{API_PREFIX}/{object_slug_for_symbol(symbol)}/"


def output_path_for_symbol(output: Path, symbol: str) -> Path:
    return output / "docs/python/api" / object_slug_for_symbol(symbol) / "index.md"


def module_route(module: str) -> str:
    return f"{API_PREFIX}/{slug_for_symbol(module)}/"


def source_revision(explicit: str | None, repository_root: Path = REPOSITORY_ROOT) -> str:
    if explicit:
        return explicit
    environment = os.environ.get("JUNJO_DOCS_REVISION")
    if environment:
        return environment
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def package_version(explicit: str | None, sdk_root: Path = SDK_ROOT) -> str:
    if explicit:
        return explicit
    with (sdk_root / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    return str(project["version"])


def load_surface(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 2:
        raise ValueError("unsupported Python API public-surface contract version")
    objects = payload.get("objects")
    if not isinstance(objects, list) or not objects:
        raise ValueError("Python API public-surface contract has no objects")
    allowed_kinds = {
        "attribute",
        "class",
        "exception",
        "function",
        "method",
        "module",
        "property",
    }
    identities: set[tuple[str, str, str]] = set()
    for entry in objects:
        if not isinstance(entry, dict) or set(entry) != {
            "kind",
            "public_name",
            "anchor",
        }:
            raise ValueError("Python API public-surface object has invalid fields")
        if entry["kind"] not in allowed_kinds:
            raise ValueError(f"unsupported Python API object kind: {entry['kind']}")
        identity = (entry["kind"], entry["public_name"], entry["anchor"])
        if identity in identities:
            raise ValueError(f"duplicate Python API public-surface object: {identity}")
        identities.add(identity)
    documented_modules = {entry["public_name"] for entry in objects if entry["kind"] == "module"}
    known_sections = {section.module: section for section in MODULE_SECTIONS}
    module_allowlist = payload.get("module_allowlist")
    if not isinstance(module_allowlist, list):
        raise ValueError("Python API public-surface contract has no module allowlist")
    if set(module_allowlist) != documented_modules:
        raise ValueError("Python API module allowlist does not match its module objects")
    unknown_modules = sorted(documented_modules - known_sections.keys())
    if unknown_modules:
        raise ValueError(f"Python API public-surface contract contains unsupported modules: {unknown_modules}")
    return payload


def module_sections_for_surface(surface: dict[str, Any]) -> tuple[ModuleSection, ...]:
    allowed = set(surface["module_allowlist"])
    return tuple(section for section in MODULE_SECTIONS if section.module in allowed)


def page_symbols(surface: dict[str, Any]) -> list[str]:
    page_kinds = {"class", "exception", "function"}
    symbols = {
        entry["anchor"]
        for entry in surface["objects"]
        if entry["kind"] in page_kinds and entry["public_name"] == entry["anchor"]
    }
    return sorted(symbols)


def page_for_entry(entry: dict[str, str], pages: list[str]) -> str | None:
    anchor = entry["anchor"]
    candidates = [page for page in pages if anchor == page or anchor.startswith(f"{page}.")]
    if not candidates:
        return None
    return max(candidates, key=len)


def resolve_object(package: Any, public_path: str) -> Any:
    relative = public_path.removeprefix("junjo.")
    obj = package[relative]
    if getattr(obj, "is_alias", False):
        obj = obj.final_target
    return obj


def replace_rst_inline(
    value: str,
    current_page: str,
    symbol_links: dict[str, tuple[str, str]],
) -> str:
    value = re.sub(r"``([^`]+)``", r"`\1`", value)

    def role_replacement(match: re.Match[str]) -> str:
        target = match.group("target").removeprefix("~")
        explicit = re.fullmatch(r"(?P<label>.+?)\s*<(?P<path>[^>]+)>", target)
        if explicit:
            label = explicit.group("label")
            target = explicit.group("path")
        else:
            label = target.rsplit(".", 1)[-1]
        candidates = [target]
        if not target.startswith("junjo."):
            candidates = [
                f"{current_page}.{target}",
                f"{current_page.rsplit('.', 1)[0]}.{target}",
                f"junjo.{target}",
            ]
        for candidate in candidates:
            link = symbol_links.get(candidate)
            if link is not None:
                route, anchor = link
                suffix = f"#{anchor}" if candidate != anchor or "." in anchor.removeprefix(current_page) else ""
                return f"[`{label}`]({route}{suffix})"
        if target.startswith("junjo."):
            return f"`{label}`"
        return f"`{label}`"

    value = re.sub(
        r":(?:class|meth|func|attr|exc|obj):`(?P<target>[^`]+)`",
        role_replacement,
        value,
    )
    value = re.sub(r":code:`([^`]+)`", r"`\1`", value)
    value = re.sub(r"`([^`<>]+)\s*<([^>]+)>`_", r"[\1](\2)", value)
    return value


def consume_rst_directive_block(lines: list[str], cursor: int) -> tuple[str, int]:
    block: list[str] = []
    while cursor < len(lines):
        line = lines[cursor]
        if line.strip() and not line.startswith((" ", "\t")):
            break
        block.append(line)
        cursor += 1
    return textwrap.dedent("\n".join(block)).strip("\n"), cursor


def render_rst_directive(kind: str, argument: str, body: str) -> list[str]:
    if kind != "code-block":
        aside = "note" if kind == "note" else "caution"
        return [f":::{aside}", body, ":::"]

    option_lines: list[str] = []
    code_lines = body.splitlines()
    while code_lines and code_lines[0].startswith(":"):
        option_lines.append(code_lines.pop(0))
    while code_lines and not code_lines[0].strip():
        code_lines.pop(0)
    caption = ""
    for option in option_lines:
        if option.startswith(":caption:"):
            caption = f" title={json_string(option.removeprefix(':caption:').strip())}"
    return [f"```{argument or 'text'}{caption}", "\n".join(code_lines).rstrip(), "```"]


def replace_rst_blocks(value: str) -> str:
    lines = value.splitlines()
    output: list[str] = []
    cursor = 0
    while cursor < len(lines):
        directive = re.fullmatch(
            r"\.\. (code-block|note|warning)::\s*(.*)",
            lines[cursor].strip(),
        )
        if directive is None:
            output.append(lines[cursor])
            cursor += 1
            continue
        body, cursor = consume_rst_directive_block(lines, cursor + 1)
        output.extend(
            render_rst_directive(
                directive.group(1),
                directive.group(2).strip(),
                body,
            )
        )
    return "\n".join(output)


def markdown_text(value: str, current_page: str, symbol_links: dict[str, tuple[str, str]]) -> str:
    value = replace_rst_blocks(value)
    value = replace_rst_inline(value, current_page, symbol_links)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def table_cell(value: object, current_page: str, symbol_links: dict[str, tuple[str, str]]) -> str:
    rendered = markdown_text(str(value), current_page, symbol_links) if value is not None else ""
    return rendered.replace("|", "\\|").replace("\n", "<br>")


def annotation_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def render_docstring_section(
    section: Any,
    prefix: str,
    current_page: str,
    symbol_links: dict[str, tuple[str, str]],
) -> str:
    kind = section.kind.value
    if kind == "text":
        return markdown_text(section.value, current_page, symbol_links)
    if kind == "parameters":
        table = [
            f"{prefix} Parameters",
            "",
            "| Name | Type | Description | Default |",
            "| --- | --- | --- | --- |",
        ]
        for item in section.value:
            default = getattr(item, "value", None)
            table.append(
                "| "
                + " | ".join(
                    (
                        f"`{item.name}`",
                        f"`{table_cell(annotation_text(item.annotation), current_page, symbol_links)}`"
                        if item.annotation
                        else "",
                        table_cell(item.description, current_page, symbol_links),
                        f"`{table_cell(default, current_page, symbol_links)}`" if default is not None else "",
                    )
                )
                + " |"
            )
        return "\n".join(table)
    if kind == "returns":
        output = [f"{prefix} Returns"]
        for item in section.value:
            annotation = annotation_text(item.annotation)
            label = f"`{annotation}`" if annotation else "Value"
            description = markdown_text(item.description, current_page, symbol_links)
            output.append(f"- **{label}:** {description}" if description else f"- {label}")
        return "\n\n".join(output)
    if kind == "raises":
        table = [f"{prefix} Raises", "", "| Exception | Description |", "| --- | --- |"]
        for item in section.value:
            table.append(
                f"| `{table_cell(item.annotation, current_page, symbol_links)}` | "
                f"{table_cell(item.description, current_page, symbol_links)} |"
            )
        return "\n".join(table)
    raise ValueError(f"unsupported Griffe docstring section: {kind}")


def render_docstring(
    docstring: Any,
    heading_level: int,
    current_page: str,
    symbol_links: dict[str, tuple[str, str]],
) -> str:
    if docstring is None:
        return ""
    rendered = (
        render_docstring_section(
            section,
            "#" * heading_level,
            current_page,
            symbol_links,
        )
        for section in docstring.parsed
    )
    return "\n\n".join(part for part in rendered if part).strip()


def source_link(obj: Any, revision: str, repository_root: Path) -> str | None:
    filepath = getattr(obj, "filepath", None)
    lineno = getattr(obj, "lineno", None)
    if filepath is None or lineno is None:
        return None
    path = Path(filepath).resolve()
    try:
        relative = path.relative_to(repository_root)
    except ValueError:
        return None
    return f"https://github.com/mdrideout/junjo/blob/{revision}/{relative.as_posix()}#L{lineno}"


def signature_for(obj: Any) -> str | None:
    if hasattr(obj, "signature"):
        try:
            return str(obj.signature())
        except (AttributeError, TypeError, ValueError):
            return None
    annotation = getattr(obj, "annotation", None)
    if annotation is not None:
        return f"{obj.name}: {annotation}"
    value = getattr(obj, "value", None)
    if value is not None:
        return f"{obj.name} = {value}"
    return None


def member_lookup(obj: Any, name: str) -> Any | None:
    members = getattr(obj, "members", {})
    candidate = members.get(name)
    if candidate is None:
        inherited = getattr(obj, "inherited_members", {})
        candidate = inherited.get(name)
    if candidate is None:
        return None
    if getattr(candidate, "is_alias", False):
        try:
            candidate = candidate.final_target
        except Exception:
            return None
    return candidate


def render_member(
    public_path: str,
    page_path: str,
    member: Any,
    kind: str,
    revision: str,
    repository_root: Path,
    symbol_links: dict[str, tuple[str, str]],
) -> str:
    name = public_path.rsplit(".", 1)[-1]
    output = [f'<a id="{html.escape(public_path, quote=True)}"></a>', f"### `{name}`", ""]
    signature = signature_for(member)
    if signature:
        output.extend(("```python", signature, "```", ""))
    link = source_link(member, revision, repository_root)
    if link:
        output.extend((f"[View source]({link})", ""))
    docs = render_docstring(getattr(member, "docstring", None), 4, page_path, symbol_links)
    if docs:
        output.append(docs)
    elif kind in {"attribute", "property"}:
        output.append("Public attribute.")
    else:
        output.append("Public member documented by its signature.")
    return "\n".join(output).rstrip()


def render_object_members(
    *,
    public_path: str,
    obj: Any,
    entries: list[dict[str, str]],
    revision: str,
    repository_root: Path,
    symbol_links: dict[str, tuple[str, str]],
) -> list[str]:
    member_entries = [
        entry
        for entry in entries
        if entry["anchor"].startswith(f"{public_path}.") and entry["public_name"] == entry["anchor"]
    ]
    rendered_members: list[tuple[int, str, str]] = []
    for entry in member_entries:
        member_name = entry["anchor"].removeprefix(f"{public_path}.").split(".", 1)[0]
        member = member_lookup(obj, member_name)
        if member is None:
            raise ValueError(f"Griffe could not resolve public member {entry['anchor']}")
        lineno = getattr(member, "lineno", sys.maxsize) or sys.maxsize
        rendered_members.append(
            (
                lineno,
                member_name,
                render_member(
                    entry["anchor"],
                    public_path,
                    member,
                    entry["kind"],
                    revision,
                    repository_root,
                    symbol_links,
                ),
            )
        )
    if not rendered_members:
        return []

    output = ["## Members", ""]
    seen: set[str] = set()
    for _, member_name, rendered in sorted(rendered_members):
        if member_name in seen:
            continue
        seen.add(member_name)
        output.extend((rendered, ""))
    return output


def render_object_page(
    public_path: str,
    obj: Any,
    entries: list[dict[str, str]],
    version: str,
    revision: str,
    channel: str,
    repository_root: Path,
    symbol_links: dict[str, tuple[str, str]],
) -> str:
    title = public_path.rsplit(".", 1)[-1]
    object_kind = next(entry["kind"] for entry in entries if entry["anchor"] == public_path)
    kind_label = object_kind.replace("exception", "exception class").title()
    description = f"Python API reference for {public_path}."
    output = [
        "---",
        f"title: {json_string(title)}",
        f"description: {json_string(description)}",
        "sidebar:",
        f"  label: {json_string(title)}",
        "---",
        "",
        f"<!-- generated-by: Griffe; sdk-version: {version}; source-revision: {revision}; channel: {channel} -->",
        f'<a id="{html.escape(public_path, quote=True)}"></a>',
        "",
        f"`{public_path}`",
        "",
        f"**Kind:** {kind_label}",
        "",
        f"**SDK version:** `{version}`",
        "",
        f"**Documentation channel:** {'Next source preview' if channel == 'next' else 'Stable release'}",
        "",
    ]
    signature = signature_for(obj)
    if signature:
        output.extend(("## Signature", "", "```python", signature, "```", ""))
    link = source_link(obj, revision, repository_root)
    if link:
        output.extend((f"[View source]({link})", ""))
    docs = render_docstring(getattr(obj, "docstring", None), 2, public_path, symbol_links)
    if docs:
        output.extend((docs, ""))
    constructor = member_lookup(obj, "__init__") if getattr(obj, "kind", None) == griffe.Kind.CLASS else None
    if constructor is not None and getattr(constructor, "docstring", None) is not None:
        constructor_docs = render_docstring(constructor.docstring, 3, public_path, symbol_links)
        if constructor_docs:
            output.extend(("## Constructor", "", constructor_docs, ""))

    output.extend(
        render_object_members(
            public_path=public_path,
            obj=obj,
            entries=entries,
            revision=revision,
            repository_root=repository_root,
            symbol_links=symbol_links,
        )
    )
    return "\n".join(output).rstrip() + "\n"


def render_module_page(
    section: ModuleSection,
    symbols: list[str],
    version: str,
    revision: str,
    channel: str,
) -> str:
    output = [
        "---",
        f"title: {json_string(section.title)}",
        f"description: {json_string(f'Python API reference for {section.module}.')}",
        "---",
        "",
        f"<!-- generated-by: Griffe; sdk-version: {version}; source-revision: {revision}; channel: {channel} -->",
        f'<a id="module-{html.escape(section.module, quote=True)}"></a>',
        "",
        f"Module: `{section.module}`",
        "",
        f"**Documentation channel:** {'Next source preview' if channel == 'next' else 'Stable release'}",
        "",
    ]
    if section.introduction:
        output.extend((section.introduction, ""))
    for symbol in symbols:
        output.append(f"- [`{symbol}`]({route_for_symbol(symbol)})")
    return "\n".join(output).rstrip() + "\n"


def render_api_index(
    sections: list[tuple[ModuleSection, list[str]]],
    version: str,
    revision: str,
    channel: str,
) -> str:
    has_agents = any(section.module.startswith("junjo.agent.") for section, _ in sections)
    output = [
        "---",
        'title: "Python API Reference"',
        'description: "Generated reference for the public Junjo Python SDK API."',
        "---",
        "",
        f"<!-- generated-by: Griffe; sdk-version: {version}; source-revision: {revision}; channel: {channel} -->",
        '<a id="api"></a>',
        "",
        f"Reference for Junjo Python SDK `{version}`.",
        "",
        f"**Documentation channel:** {'Next source preview' if channel == 'next' else 'Stable release'}",
        "",
        (
            "This preview is generated from repository source and may describe changes "
            "not yet in the published package."
            if channel == "next"
            else "This reference is generated from the released source revision."
        ),
        "",
    ]
    if has_agents:
        output.extend(
            (
                "The common Agent definition and binding types are also available from `junjo`. "
                "Provider-neutral messages, results, and typed errors live in `junjo.agent`, and "
                "deterministic scripted testing support is public at `junjo.agent.testing`.",
                "",
            )
        )
    for section, symbols in sections:
        output.extend((f"## {section.title}", "", f"Module: [`{section.module}`]({module_route(section.module)})", ""))
        if section.introduction:
            output.extend((section.introduction, ""))
        for symbol in symbols:
            output.append(f"- [`{symbol}`]({route_for_symbol(symbol)})")
        output.append("")
    return "\n".join(output).rstrip() + "\n"


def generate_api(
    output: Path,
    surface_path: Path,
    version: str,
    revision: str,
    channel: str,
    sdk_root: Path = SDK_ROOT,
) -> None:
    surface = load_surface(surface_path)
    module_sections = module_sections_for_surface(surface)
    repository_root = sdk_root.parents[1]
    pages = page_symbols(surface)
    surface_entries: list[dict[str, str]] = surface["objects"]
    symbol_links: dict[str, tuple[str, str]] = {}
    for entry in surface_entries:
        if entry["kind"] == "module":
            symbol_links[entry["public_name"]] = (
                module_route(entry["public_name"]),
                entry["anchor"],
            )
            continue
        page = page_for_entry(entry, pages)
        if page is None:
            continue
        link = (route_for_symbol(page), entry["anchor"])
        symbol_links[entry["public_name"]] = link
        symbol_links[entry["anchor"]] = link
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        package = griffe.load("junjo", search_paths=[sdk_root / "src"], docstring_parser="auto")

    output.mkdir(parents=True, exist_ok=True)
    manifest_symbols: list[dict[str, str]] = []
    for public_path in pages:
        with contextlib.redirect_stderr(stderr):
            obj = resolve_object(package, public_path)
            page_content = render_object_page(
                public_path,
                obj,
                surface_entries,
                version,
                revision,
                channel,
                repository_root,
                symbol_links,
            )
        path = output_path_for_symbol(output, public_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(page_content, encoding="utf-8")

    sections: list[tuple[ModuleSection, list[str]]] = []
    for section in module_sections:
        symbols = [
            page
            for page in pages
            if page.startswith(f"{section.module}.") and len(page.split(".")) == len(section.module.split(".")) + 1
        ]
        sections.append((section, symbols))
        module_path = output / "docs/python/api" / slug_for_symbol(section.module) / "index.md"
        module_path.parent.mkdir(parents=True, exist_ok=True)
        module_path.write_text(
            render_module_page(section, symbols, version, revision, channel),
            encoding="utf-8",
        )

    index_path = output / "docs/python/api/index.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(render_api_index(sections, version, revision, channel), encoding="utf-8")

    unmapped: list[str] = []
    for entry in surface_entries:
        if entry["kind"] == "module":
            target_route = module_route(entry["public_name"])
            target_anchor = entry["anchor"]
        else:
            page = page_for_entry(entry, pages)
            if page is None:
                unmapped.append(f"{entry['kind']} {entry['public_name']} ({entry['anchor']})")
                continue
            target_route = route_for_symbol(page)
            target_anchor = entry["anchor"]
        manifest_symbols.append(
            {
                "kind": entry["kind"],
                "public_name": entry["public_name"],
                "target_route": target_route,
                "target_anchor": target_anchor,
            }
        )
    if unmapped:
        raise ValueError("Python API public objects have no generated page:\n" + "\n".join(unmapped))

    module_page_count = len(sections)
    symbol_page_count = len(pages)
    page_count = symbol_page_count + module_page_count + 1
    manifest = {
        "version": 2,
        "sdk": "python",
        "sdk_version": version,
        "source_revision": revision,
        "channel": channel,
        "generator": f"griffe-{distribution_version('griffe')}",
        "docstring_parser": "auto",
        "public_surface_hash": sha256_bytes(surface_path.read_bytes()),
        "page_count": page_count,
        "symbol_page_count": symbol_page_count,
        "module_page_count": module_page_count,
        "symbol_count": len(manifest_symbols),
        "symbols": manifest_symbols,
        "griffe_diagnostics": [
            line.replace(f"{repository_root.resolve()}/", "") for line in stderr.getvalue().splitlines() if line.strip()
        ],
    }
    manifest_path = output / "api-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {page_count} API pages covering {len(manifest_symbols)} public Python objects.")


def check_generation(
    output: Path,
    surface: Path,
    version: str,
    revision: str,
    channel: str,
    sdk_root: Path = SDK_ROOT,
) -> None:
    with tempfile_directory() as temporary:
        expected_root = temporary / "expected"
        generate_api(expected_root, surface, version, revision, channel, sdk_root)
        expected_files = {
            path.relative_to(expected_root): path.read_bytes() for path in expected_root.rglob("*") if path.is_file()
        }
        actual_files = {path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()}
        if expected_files.keys() != actual_files.keys():
            missing = sorted(str(path) for path in expected_files.keys() - actual_files.keys())
            extra = sorted(str(path) for path in actual_files.keys() - expected_files.keys())
            raise ValueError(f"generated API file set differs; missing={missing}, extra={extra}")
        stale = [str(path) for path in expected_files if expected_files[path] != actual_files[path]]
        if stale:
            raise ValueError("stale generated API files: " + ", ".join(stale))
    print("Generated API output is deterministic and current.")


@contextlib.contextmanager
def tempfile_directory() -> Any:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="junjo-api-docs-") as directory:
        yield Path(directory)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="generate Starlight Markdown API pages")
    generate_parser.add_argument("--output", type=Path, required=True)
    generate_parser.add_argument("--surface", type=Path, default=DEFAULT_SURFACE)
    generate_parser.add_argument("--version")
    generate_parser.add_argument("--revision")
    generate_parser.add_argument("--sdk-root", type=Path, default=SDK_ROOT)
    generate_parser.add_argument(
        "--channel", choices=("next", "stable"), default=os.environ.get("JUNJO_DOCS_CHANNEL", "next")
    )
    generate_parser.add_argument("--clean", action="store_true")

    check_parser = subparsers.add_parser("check", help="verify an existing generated API export")
    check_parser.add_argument("--output", type=Path, required=True)
    check_parser.add_argument("--surface", type=Path, default=DEFAULT_SURFACE)
    check_parser.add_argument("--version")
    check_parser.add_argument("--revision")
    check_parser.add_argument("--sdk-root", type=Path, default=SDK_ROOT)
    check_parser.add_argument(
        "--channel", choices=("next", "stable"), default=os.environ.get("JUNJO_DOCS_CHANNEL", "next")
    )

    validate_parser = subparsers.add_parser(
        "validate",
        help="validate the public-surface contract and render it in a temporary directory",
    )
    validate_parser.add_argument("--surface", type=Path, default=DEFAULT_SURFACE)
    validate_parser.add_argument("--version")
    validate_parser.add_argument("--revision")
    validate_parser.add_argument("--sdk-root", type=Path, default=SDK_ROOT)
    validate_parser.add_argument(
        "--channel",
        choices=("next", "stable"),
        default=os.environ.get("JUNJO_DOCS_CHANNEL", "next"),
    )

    args = parser.parse_args()
    sdk_root = args.sdk_root.resolve()
    repository_root = sdk_root.parents[1]
    version = package_version(args.version, sdk_root)
    revision = source_revision(args.revision, repository_root)
    if args.command == "generate":
        if args.clean and args.output.exists():
            shutil.rmtree(args.output)
        generate_api(
            args.output,
            args.surface,
            version,
            revision,
            args.channel,
            sdk_root,
        )
        return 0
    if args.command == "validate":
        with tempfile_directory() as temporary:
            generate_api(
                temporary / "api",
                args.surface,
                version,
                revision,
                args.channel,
                sdk_root,
            )
        print("Validated the Python API public-surface contract with Griffe.")
        return 0
    check_generation(
        args.output,
        args.surface,
        version,
        revision,
        args.channel,
        sdk_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
