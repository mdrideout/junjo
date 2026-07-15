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
5. Assembly copies and validates `apps/website/legacy-python-api`, the
   separately deployed Cloudflare Pages source for the retired domain. Its
   single permanent rule redirects every `python-api.junjo.ai` request to
   `https://junjo.ai/docs/python/`. Never include it in the `junjo.ai` output.

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

Cloudflare Pages owns production builds through its Git integration. The
`junjo-website` project runs this version-controlled command from the repository
root:

```bash
bash tooling/docs/build_cloudflare_pages.sh
```

The build output is `apps/website/dist`. The script installs a pinned `uv`,
builds and validates the Sphinx parity source, validates the narrative ledger,
assembles the source-owned exports, runs all Starlight checks, and audits
production dependencies. GitHub Actions independently runs the same gates as a
pull-request validator, but does not upload, retain, or deploy its generated
output. Merging the validated source to protected `master` is the production
signal; Cloudflare then pulls, builds, and deploys that commit. Automatic
production builds are enabled for `master`, while Cloudflare branch previews
are disabled so unvalidated source is never deployed.

The `junjo-python-api` project runs
`tooling/docs/build_legacy_python_redirect.sh`, which waits for the unified
Python landing page before publishing the committed
`apps/website/legacy-python-api` directory. That directory contains only the
global `301` rule. Neither Pages project consumes a checked-in `dist` directory.

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
