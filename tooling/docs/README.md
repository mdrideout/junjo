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
5. Assembly emits `.docs-assembly/python-api-site`, a separately deployable
   Cloudflare Pages retirement artifact. Its single permanent rule redirects
   every `python-api.junjo.ai` request to `https://junjo.ai/docs/python/`.
   Never include this artifact in the `junjo.ai` deployment.

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

The default channel is `next`. A release workflow can set
`JUNJO_DOCS_CHANNEL=stable` only while checked out at the corresponding released
source revision. The channel is visible on API pages and recorded in both
manifests, so an unreleased source preview cannot silently masquerade as stable
documentation.

## Cloudflare deployment

The `Public Documentation` workflow is the only production build pipeline. It
assembles, validates, and uploads `apps/website/dist`, then a separate deploy
job downloads that exact artifact and publishes it to the `junjo-website`
Cloudflare Pages project. Only after that succeeds does it deploy
`.docs-assembly/python-api-site` to `junjo-python-api`, retiring the Sphinx site
with the global `301` redirect.

The GitHub `public-documentation-production` environment owns
`CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`. The token needs only
Cloudflare Pages edit access for the owning account. Cloudflare's automatic Git
deployments must be disabled when this pipeline is activated so a second build
cannot overwrite the validated artifact.

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
