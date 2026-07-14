#!/usr/bin/env python3
"""Mechanically convert Junjo's Sphinx narrative pages to Starlight Markdown.

The RST files remain the comparison baseline during the migration. This tool
owns only format conversion, provenance, and the content/route ledgers. It does
not edit prose or generate the Python API reference.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from rst_to_myst import rst_to_myst

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_DOCS = REPOSITORY_ROOT / "sdks/python/docs"
CONTENT_LEDGER = REPOSITORY_ROOT / "tooling/docs/content-migration.json"
LEGACY_ROUTES = REPOSITORY_ROOT / "tooling/docs/legacy-routes.json"


@dataclass(frozen=True)
class Page:
    source: str
    target: str | None
    route: str
    owner: str
    disposition: str = "migrated"


@dataclass(frozen=True)
class RepositorySource:
    path: str
    owner: str
    disposition: str
    target_route: str | None = None
    corrections: tuple[str, ...] = ()


PAGES = (
    Page("index.rst", "sdks/python/docs/content/docs/python/index.md", "/docs/python/", "python"),
    Page(
        "getting_started.rst",
        "sdks/python/docs/content/docs/python/get-started.md",
        "/docs/python/get-started/",
        "python",
    ),
    Page("tutorial.rst", "sdks/python/docs/content/docs/python/tutorial.md", "/docs/python/tutorial/", "python"),
    Page("agents.rst", "sdks/python/docs/content/docs/python/agents/index.md", "/docs/python/agents/", "python"),
    Page(
        "agent_testing.rst",
        "sdks/python/docs/content/docs/python/agents/testing.md",
        "/docs/python/agents/testing/",
        "python",
    ),
    Page(
        "agent_composition.rst",
        "sdks/python/docs/content/docs/python/agents/composition.md",
        "/docs/python/agents/composition/",
        "python",
    ),
    Page(
        "core_concepts.rst",
        "sdks/python/docs/content/docs/python/concepts.md",
        "/docs/python/concepts/",
        "python",
    ),
    Page(
        "state_management.rst",
        "sdks/python/docs/content/docs/python/workflows/state.md",
        "/docs/python/workflows/state/",
        "python",
    ),
    Page(
        "concurrency.rst",
        "sdks/python/docs/content/docs/python/workflows/concurrency.md",
        "/docs/python/workflows/concurrency/",
        "python",
    ),
    Page(
        "subflows.rst",
        "sdks/python/docs/content/docs/python/workflows/subflows.md",
        "/docs/python/workflows/subflows/",
        "python",
    ),
    Page("hooks.rst", "sdks/python/docs/content/docs/python/hooks.md", "/docs/python/hooks/", "python"),
    Page(
        "visualizing_workflows.rst",
        "sdks/python/docs/content/docs/python/workflows/visualization.md",
        "/docs/python/workflows/visualization/",
        "python",
    ),
    Page(
        "eval_driven_dev.rst",
        "sdks/python/docs/content/docs/python/testing/eval-driven-development.md",
        "/docs/python/testing/eval-driven-development/",
        "python",
    ),
    Page("api.rst", None, "/docs/python/api/", "python", "generated"),
    Page(
        "junjo_ai_studio.rst",
        "apps/studio/docs/public/docs/studio/overview.md",
        "/docs/studio/overview/",
        "studio",
    ),
    Page(
        "docker_reference.rst",
        "apps/studio/docs/public/docs/studio/docker-reference.md",
        "/docs/studio/docker-reference/",
        "studio",
    ),
    Page(
        "deployment.rst",
        "apps/studio/docs/public/docs/studio/deployment.md",
        "/docs/studio/deployment/",
        "studio",
    ),
    Page(
        "opentelemetry.rst",
        "sdks/python/docs/content/docs/observability/opentelemetry.md",
        "/docs/observability/opentelemetry/",
        "python",
    ),
)


REPOSITORY_SOURCES = (
    RepositorySource(
        "apps/website/src/content/docs/index.mdx",
        "website",
        "retained",
        "/",
        (
            "Replaced obsolete junjo-server links with the canonical monorepo Studio path.",
            "Replaced the separate Python-docs call to action with the unified /docs/ route.",
        ),
    ),
    RepositorySource("apps/website/src/content/docs/guides/example.md", "website", "retained", "/guides/example/"),
    RepositorySource(
        "apps/website/src/content/docs/reference/example.md",
        "website",
        "retained",
        "/reference/example/",
    ),
    RepositorySource("sdks/python/README.md", "python", "canonical-linked"),
    RepositorySource("sdks/python/examples/getting_started/README.md", "python", "canonical-linked"),
    RepositorySource("sdks/python/examples/base/README.md", "python", "canonical-linked"),
    RepositorySource("sdks/python/examples/ai_chat/README.md", "python", "canonical-linked"),
    RepositorySource("sdks/python/examples/ai_chat/backend/README.md", "python", "canonical-linked"),
    RepositorySource("sdks/python/examples/ai_chat/frontend/README.md", "python", "canonical-linked"),
    RepositorySource("apps/studio/README.md", "studio", "canonical-linked"),
    RepositorySource("apps/studio/deployments/minimal/README.md", "studio", "canonical-linked"),
    RepositorySource("apps/studio/deployments/vm-caddy/README.md", "studio", "canonical-linked"),
    RepositorySource("contracts/telemetry/README.md", "telemetry", "canonical-linked"),
)


DOC_ROUTES = {page.source.removesuffix(".rst"): page.route for page in PAGES}
DOC_ROUTES.update(
    {
        "index": "/docs/python/",
        "visualizing_workflows": "/docs/python/workflows/visualization/",
    }
)


def sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def yaml_string(value: str) -> str:
    # JSON strings are valid YAML scalar strings and make escaping deterministic.
    return json.dumps(value, ensure_ascii=False)


def extract_meta(source: str) -> tuple[str | None, str | None]:
    description = None
    keywords = None
    lines = source.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != ".. meta::":
            continue
        cursor = index + 1
        while cursor < len(lines) and (not lines[cursor].strip() or lines[cursor].startswith((" ", "\t"))):
            stripped = lines[cursor].strip()
            if stripped.startswith(":description:"):
                description = stripped.removeprefix(":description:").strip()
            elif stripped.startswith(":keywords:"):
                keywords = stripped.removeprefix(":keywords:").strip()
            cursor += 1
        break
    return description, keywords


def extract_title(markdown: str, source_name: str) -> tuple[str, str]:
    match = re.search(r"^# (.+)$", markdown, flags=re.MULTILINE)
    if match is None:
        raise ValueError(f"{source_name}: converted output has no level-one heading")
    title = match.group(1).strip()
    body = markdown[: match.start()] + markdown[match.end() :]
    return title, body.lstrip("\n")


def replace_eval_rst(markdown: str) -> str:
    pattern = re.compile(r"```\{eval-rst\}\n(?P<body>.*?)\n```", flags=re.DOTALL)

    def replacement(match: re.Match[str]) -> str:
        body = match.group("body")
        if re.search(r"^\.\. (?:meta|toctree)::", body, flags=re.MULTILINE):
            return ""
        raise ValueError(f"unhandled eval-rst block:\n{body}")

    return pattern.sub(replacement, markdown)


def replace_code_directives(markdown: str) -> str:
    pattern = re.compile(
        r"```\{code-block\}\s+(?P<language>[^\n]+)\n"
        r"(?P<options>(?::[^\n]+\n)*)"
        r"\n?(?P<code>.*?)\n```",
        flags=re.DOTALL,
    )

    def replacement(match: re.Match[str]) -> str:
        language = match.group("language").strip()
        options = match.group("options")
        caption_match = re.search(r"^:caption:\s*(.+)$", options, flags=re.MULTILINE)
        caption = f" title={yaml_string(caption_match.group(1).strip())}" if caption_match else ""
        return f"```{language}{caption}\n{match.group('code').rstrip()}\n```"

    return pattern.sub(replacement, markdown)


def replace_image_directives(markdown: str) -> str:
    pattern = re.compile(
        r"```\{image\}\s+(?P<path>[^\n]+)\n"
        r"(?P<options>(?::[^\n]+\n)*)"
        r"```",
        flags=re.DOTALL,
    )

    def replacement(match: re.Match[str]) -> str:
        source_path = match.group("path").strip()
        name = Path(source_path).name
        options = match.group("options")
        option_values = {
            option.group("name"): option.group("value").strip()
            for option in re.finditer(r"^:(?P<name>[a-z-]+):\s*(?P<value>.+)$", options, flags=re.MULTILINE)
        }
        alt = html.escape(option_values.get("alt", name), quote=True)
        styles = ["max-width: 100%"]
        width = option_values.get("width")
        if width:
            styles.append(f"width: {width}")
        if option_values.get("align") == "center":
            styles.extend(("display: block", "margin-inline: auto"))
        style = "; ".join(styles)
        source = html.escape(name, quote=True)
        return f'<img src="/docs-assets/generated/python/{source}" alt="{alt}" style="{style}" />'

    return pattern.sub(replacement, markdown)


def replace_directive_fences(markdown: str) -> str:
    markdown = re.sub(r"^:::\{note\}\s*$", ":::note", markdown, flags=re.MULTILINE)
    markdown = re.sub(r"^:::\{warning\}\s*$", ":::caution", markdown, flags=re.MULTILINE)
    return markdown


def api_route_for_role(target: str) -> str:
    normalized = target.removeprefix("~")
    public_aliases = {
        "junjo.correlation.ExecutionCorrelation": "junjo.ExecutionCorrelation",
    }
    public_path = public_aliases.get(normalized, normalized)
    return "/docs/python/api/" + "/".join(part.lower() for part in public_path.split(".")) + "/"


def replace_roles(markdown: str) -> str:
    def doc_replacement(match: re.Match[str]) -> str:
        value = match.group("value")
        explicit = re.fullmatch(r"(?P<label>.+?)\s*<(?P<target>[^>]+)>", value)
        if explicit:
            label = explicit.group("label")
            target = explicit.group("target")
        else:
            target = value
            label = target.replace("_", " ").title()
        route = DOC_ROUTES.get(target)
        if route is None:
            raise ValueError(f"unmapped Sphinx doc role target: {target}")
        return f"[{label}]({route})"

    markdown = re.sub(r"\{doc\}`(?P<value>[^`]+)`", doc_replacement, markdown)

    def api_replacement(match: re.Match[str]) -> str:
        target = match.group("target")
        label = target.removeprefix("~").rsplit(".", 1)[-1]
        return f"[`{label}`]({api_route_for_role(target)})"

    markdown = re.sub(r"\{(?:class|meth|func|attr)\}`(?P<target>[^`]+)`", api_replacement, markdown)
    markdown = re.sub(r"\{code\}`(?P<value>[^`]+)`", lambda match: f"`{match.group('value')}`", markdown)
    return markdown


def normalize_markdown(markdown: str) -> str:
    markdown = replace_eval_rst(markdown)
    markdown = replace_code_directives(markdown)
    markdown = replace_image_directives(markdown)
    markdown = replace_directive_fences(markdown)
    markdown = replace_roles(markdown)
    markdown = re.sub(r"^\((?P<label>[^)]+)\)=\s*$", r'<a id="\g<label>"></a>', markdown, flags=re.MULTILINE)
    markdown = re.sub(r"^(?P<indent>\s*): - ", r"\g<indent>  - ", markdown, flags=re.MULTILINE)
    markdown = re.sub(r"^\\- (?=\*\*)", "- ", markdown, flags=re.MULTILINE)
    markdown = re.sub(r"(?m)^(\*\*[^\n]+:\*\*)\n(?=- )", r"\1\n\n", markdown)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    unsupported = re.findall(r"```\{[^\n]+|\{[a-zA-Z0-9_-]+\}`", markdown)
    if unsupported:
        raise ValueError(f"converted Markdown contains unsupported MyST constructs: {sorted(set(unsupported))}")
    return markdown.strip() + "\n"


def convert_page(page: Page) -> str:
    source_path = PYTHON_DOCS / page.source
    source = source_path.read_text(encoding="utf-8")
    warnings = io.StringIO()
    converted = rst_to_myst(
        source,
        warning_stream=warnings,
        use_sphinx=False,
        raise_on_warning=True,
        colon_fences=True,
    ).text
    if warnings.getvalue().strip():
        raise ValueError(f"{page.source}: RST conversion warnings:\n{warnings.getvalue()}")
    title, body = extract_title(converted, page.source)
    description, keywords = extract_meta(source)
    body = normalize_markdown(body)
    source_hash = sha256_text(source)
    frontmatter = ["---", f"title: {yaml_string(title)}"]
    if description:
        frontmatter.append(f"description: {yaml_string(description)}")
    frontmatter.extend(("---", ""))
    provenance = f"<!-- migrated-from: sdks/python/docs/{page.source}; source-hash: {source_hash} -->"
    if keywords:
        provenance += f"\n<!-- migrated-keywords: {html.escape(keywords)} -->"
    return "\n".join(frontmatter) + provenance + "\n\n" + body


def source_directive_blocks(source: str, directive: str) -> list[str]:
    lines = source.splitlines()
    blocks: list[str] = []
    cursor = 0
    prefix = f".. {directive}::"
    while cursor < len(lines):
        if not lines[cursor].lstrip().startswith(prefix):
            cursor += 1
            continue
        indent = len(lines[cursor]) - len(lines[cursor].lstrip())
        block = [lines[cursor]]
        cursor += 1
        while cursor < len(lines):
            line = lines[cursor]
            if not line.strip():
                block.append(line)
                cursor += 1
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= indent:
                break
            block.append(line)
            cursor += 1
        blocks.append("\n".join(block).rstrip())
    return blocks


def heading_inventory(source: str) -> list[dict[str, str | int]]:
    lines = source.splitlines()
    headings: list[dict[str, str | int]] = []
    levels: dict[str, int] = {}
    for index in range(len(lines) - 1):
        title = lines[index].strip()
        underline = lines[index + 1].strip()
        if not title or not underline or len(underline) < len(title):
            continue
        if len(set(underline)) != 1 or underline[0] not in "=-~^\"'`:+*#":
            continue
        marker = underline[0]
        if marker not in levels:
            levels[marker] = len(levels) + 1
        headings.append({"title": title, "level": levels[marker], "source_line": index + 1})
    return headings


def ledger_record(page: Page, converted: str | None) -> dict[str, object]:
    source_path = PYTHON_DOCS / page.source
    source = source_path.read_text(encoding="utf-8")
    directives = re.findall(r"^\s*\.\. ([a-zA-Z0-9_-]+)::", source, flags=re.MULTILINE)
    anchors = re.findall(r"^\.\. _([^:]+):", source, flags=re.MULTILINE)
    images = re.findall(r"^\s*\.\. image::\s+(.+)$", source, flags=re.MULTILINE)
    roles = [
        {"role": match.group("role"), "target": match.group("target")}
        for match in re.finditer(r":(?P<role>[a-zA-Z0-9_-]+):`(?P<target>[^`]+)`", source)
    ]
    links = sorted(set(re.findall(r"https?://[^\s>`]+", source)))
    code_blocks = source_directive_blocks(source, "code-block")
    return {
        "source_path": str(source_path.relative_to(REPOSITORY_ROOT)),
        "source_hash": sha256_text(source),
        "source_lines": len(source.splitlines()),
        "owner": page.owner,
        "disposition": page.disposition,
        "target_path": page.target,
        "target_route": page.route,
        "target_hash": sha256_text(converted) if converted is not None else None,
        "status": "converted" if converted is not None else "awaiting-api-generation",
        "headings": heading_inventory(source),
        "anchors": anchors,
        "directive_counts": {name: directives.count(name) for name in sorted(set(directives))},
        "code_blocks": [sha256_text(block) for block in code_blocks],
        "images": images,
        "roles": roles,
        "outbound_links": links,
    }


def legacy_route_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for page in PAGES:
        stem = page.source.removesuffix(".rst")
        source_routes = [f"/{stem}.html", f"/{stem}"]
        if stem == "index":
            source_routes.extend(("/", "/index.html"))
        source = (PYTHON_DOCS / page.source).read_text(encoding="utf-8")
        records.append(
            {
                "source_document": page.source,
                "source_routes": sorted(set(source_routes)),
                "target_route": page.route,
                "legacy_anchors": re.findall(r"^\.\. _([^:]+):", source, flags=re.MULTILINE),
                "status": "mapped",
            }
        )
    return records


def repository_source_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for source in REPOSITORY_SOURCES:
        path = REPOSITORY_ROOT / source.path
        content = path.read_text(encoding="utf-8")
        records.append(
            {
                "source_path": source.path,
                "source_hash": sha256_text(content),
                "source_lines": len(content.splitlines()),
                "owner": source.owner,
                "disposition": source.disposition,
                "target_route": source.target_route,
                "corrections": list(source.corrections),
                "status": "accounted-for",
            }
        )
    return records


def expected_outputs() -> dict[Path, str]:
    outputs: dict[Path, str] = {}
    ledger: list[dict[str, object]] = []
    for page in PAGES:
        converted = convert_page(page) if page.target is not None else None
        if page.target is not None and converted is not None:
            outputs[REPOSITORY_ROOT / page.target] = converted
        ledger.append(ledger_record(page, converted))
    outputs[CONTENT_LEDGER] = (
        json.dumps(
            {"version": 1, "pages": ledger, "repository_sources": repository_source_records()},
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    outputs[LEGACY_ROUTES] = (
        json.dumps({"version": 1, "routes": legacy_route_records()}, indent=2, ensure_ascii=False) + "\n"
    )
    return outputs


def write_outputs(outputs: dict[Path, str]) -> None:
    managed_roots = (
        REPOSITORY_ROOT / "sdks/python/docs/content",
        REPOSITORY_ROOT / "apps/studio/docs/public",
    )
    for root in managed_roots:
        if root.exists():
            shutil.rmtree(root)
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def check_outputs(outputs: dict[Path, str]) -> int:
    failures: list[str] = []
    for path, expected in outputs.items():
        if not path.exists():
            failures.append(f"missing generated migration output: {path.relative_to(REPOSITORY_ROOT)}")
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            failures.append(f"stale generated migration output: {path.relative_to(REPOSITORY_ROOT)}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"Validated {len(PAGES)} RST migration records and {len(outputs) - 2} converted pages.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write converted content and migration ledgers")
    mode.add_argument("--check", action="store_true", help="verify committed output is current")
    args = parser.parse_args()

    outputs = expected_outputs()
    if args.write:
        write_outputs(outputs)
        print(f"Wrote {len(outputs) - 2} converted pages and two migration ledgers.")
        return 0
    return check_outputs(outputs)


if __name__ == "__main__":
    raise SystemExit(main())
