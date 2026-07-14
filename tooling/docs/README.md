# Unified documentation tooling

This directory contains the repository-level migration and assembly boundary
for the unified Starlight documentation site. It does not own SDK prose or
product documentation.

## Pipeline

1. `migrate_rst.py` mechanically converts every inventoried Sphinx narrative
   page into source-owned Markdown and writes `content-migration.json` plus
   `legacy-routes.json`.
2. `sdks/python/docs/export_api.py` uses Griffe to export the exact public
   Python API represented by the committed Sphinx baseline.
3. `assemble_public_docs.py` merges Python content, Studio content, API pages,
   assets, and manifests into ignored staging directories under
   `apps/website`.
4. Astro/Starlight builds one immutable deployable. The post-build validator
   checks all routes, anchors, links, search output, sitemap output, migration
   entries, and Sphinx API objects.
5. Assembly emits `.docs-assembly/python-api._redirects`, a reversible
   Cloudflare Pages compatibility artifact for the legacy domain. Never deploy
   that file on `junjo.ai`; deploy it on `python-api.junjo.ai` only after the
   roadmap's parallel validation gate.

Run the converter in its isolated dependency environment:

```bash
uv sync --project tooling/docs --frozen
uv run --project tooling/docs python tooling/docs/migrate_rst.py --check
```

Refresh mechanical content only after reviewing source changes:

```bash
uv run --project tooling/docs python tooling/docs/migrate_rst.py --write
```

Assemble or verify the ignored Starlight staging tree:

```bash
python3 tooling/docs/assemble_public_docs.py --write
python3 tooling/docs/assemble_public_docs.py --check
```

## Language SDK artifact contract

Each SDK owns its extraction dependency, lockfile, public-symbol policy, and
generated documentation. The repository assembler consumes an artifact with:

- Markdown rooted at `docs/<language>/api/`;
- an API manifest containing generator version, SDK version, immutable source
  revision, page count, symbol count, and one stable route/anchor entry per
  public symbol;
- source links pinned to the same immutable revision; and
- a check mode that proves byte-for-byte deterministic generation.

The Python implementation is the reference contract. A future TypeScript SDK
should implement the same boundary with TypeDoc in that SDK's own dependency
graph. TypeDoc is not added before a TypeScript SDK exists. Narrative examples
may use synchronized Starlight language tabs only when multiple SDKs implement
the same concept; API reference pages stay language-specific so symbols remain
searchable and deep-linkable.
