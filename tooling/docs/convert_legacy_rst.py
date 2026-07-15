#!/usr/bin/env python3
"""Convert RST narrative content from a pre-migration SDK release.

Current documentation is owned Markdown. This isolated converter exists only
so the stable portal can render an immutable SDK release that predates that
contract; it never writes current source documentation.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

from rst_to_myst import rst_to_myst

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Page:
    source: str
    target: str | None
    route: str
    owner: str
    disposition: str = "migrated"


PAGES = (
    Page(
        "index.rst",
        "sdks/python/docs/content/docs/python/index.md",
        "/docs/python/",
        "python",
    ),
    Page(
        "getting_started.rst",
        "sdks/python/docs/content/docs/python/get-started.md",
        "/docs/python/get-started/",
        "python",
    ),
    Page(
        "tutorial.rst",
        "sdks/python/docs/content/docs/python/tutorial.md",
        "/docs/python/tutorial/",
        "python",
    ),
    Page(
        "agents.rst",
        "sdks/python/docs/content/docs/python/agents/index.md",
        "/docs/python/agents/",
        "python",
    ),
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
    Page(
        "hooks.rst",
        "sdks/python/docs/content/docs/python/hooks.md",
        "/docs/python/hooks/",
        "python",
    ),
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
    Page(
        "opentelemetry.rst",
        "sdks/python/docs/content/docs/observability/opentelemetry.md",
        "/docs/observability/opentelemetry/",
        "python",
    ),
)


DOC_ROUTES = {page.source.removesuffix(".rst"): page.route for page in PAGES}
DOC_ROUTES.update(
    {
        "api": "/docs/python/api/",
        "deployment": "/docs/studio/deployment/",
        "docker_reference": "/docs/studio/docker-reference/",
        "index": "/docs/python/",
        "junjo_ai_studio": "/docs/studio/overview/",
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
        while cursor < len(lines) and (
            not lines[cursor].strip() or lines[cursor].startswith((" ", "\t"))
        ):
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
        caption = (
            f" title={yaml_string(caption_match.group(1).strip())}"
            if caption_match
            else ""
        )
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
            for option in re.finditer(
                r"^:(?P<name>[a-z-]+):\s*(?P<value>.+)$", options, flags=re.MULTILINE
            )
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
    markdown = re.sub(
        r"^:::\{warning\}\s*$", ":::caution", markdown, flags=re.MULTILINE
    )
    return markdown


def api_route_for_role(target: str) -> str:
    normalized = target.removeprefix("~")
    public_aliases = {
        "junjo.correlation.ExecutionCorrelation": "junjo.ExecutionCorrelation",
    }
    public_path = public_aliases.get(normalized, normalized)
    return (
        "/docs/python/api/"
        + "/".join(part.lower() for part in public_path.split("."))
        + "/"
    )


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
            raise ValueError(f"unmapped legacy RST doc role target: {target}")
        return f"[{label}]({route})"

    markdown = re.sub(r"\{doc\}`(?P<value>[^`]+)`", doc_replacement, markdown)

    def api_replacement(match: re.Match[str]) -> str:
        target = match.group("target")
        label = target.removeprefix("~").rsplit(".", 1)[-1]
        return f"[`{label}`]({api_route_for_role(target)})"

    markdown = re.sub(
        r"\{(?:class|meth|func|attr)\}`(?P<target>[^`]+)`", api_replacement, markdown
    )
    markdown = re.sub(
        r"\{code\}`(?P<value>[^`]+)`",
        lambda match: f"`{match.group('value')}`",
        markdown,
    )
    return markdown


def normalize_markdown(markdown: str) -> str:
    markdown = replace_eval_rst(markdown)
    markdown = replace_code_directives(markdown)
    markdown = replace_image_directives(markdown)
    markdown = replace_directive_fences(markdown)
    markdown = replace_roles(markdown)
    markdown = re.sub(
        r"^\((?P<label>[^)]+)\)=\s*$",
        r'<a id="\g<label>"></a>',
        markdown,
        flags=re.MULTILINE,
    )
    markdown = re.sub(
        r"^(?P<indent>\s*): - ", r"\g<indent>  - ", markdown, flags=re.MULTILINE
    )
    markdown = re.sub(r"^\\- (?=\*\*)", "- ", markdown, flags=re.MULTILINE)
    markdown = re.sub(r"(?m)^(\*\*[^\n]+:\*\*)\n(?=- )", r"\1\n\n", markdown)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    unsupported = re.findall(r"```\{[^\n]+|\{[a-zA-Z0-9_-]+\}`", markdown)
    if unsupported:
        raise ValueError(
            f"converted Markdown contains unsupported MyST constructs: {sorted(set(unsupported))}"
        )
    return markdown.strip() + "\n"


def convert_page(page: Page, source_docs: Path) -> str:
    source_path = source_docs / page.source
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
        raise ValueError(
            f"{page.source}: RST conversion warnings:\n{warnings.getvalue()}"
        )
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


def export_release_content(source_docs: Path, output: Path) -> int:
    """Convert the Python-owned RST present in a pre-migration SDK release."""
    converted_pages = 0
    for page in PAGES:
        if page.owner != "python" or page.target is None:
            continue
        source_path = source_docs / page.source
        if not source_path.is_file():
            continue
        target = Path(page.target).relative_to("sdks/python/docs/content")
        destination = output / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(convert_page(page, source_docs), encoding="utf-8")
        converted_pages += 1
    if converted_pages == 0:
        raise ValueError(f"no Python RST documentation was found below {source_docs}")
    print(f"Exported {converted_pages} released RST pages to {output}.")
    return converted_pages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-docs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export_release_content(args.source_docs.resolve(), args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
