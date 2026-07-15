# Junjo website

This directory owns the public Junjo website and unified Starlight
documentation renderer at [junjo.ai](https://junjo.ai/). Its Node dependency
graph remains independent inside the Junjo platform repository.

The website explains how the platform components fit together and publishes
source-owned SDK and Studio documentation exports. Detailed Python SDK API and
implementation documentation remains owned by `sdks/python/docs`; Studio
runtime code and deployment packages remain owned by `apps/studio`. Generated
content staged below `src/content/docs/generated` is never edited here.

## Requirements

- Node.js 22.12 or newer
- npm 9.6.5 or newer
- Python 3.13 and `uv` for the complete documentation assembly

## Development

Run commands from `apps/website`:

```bash
npm ci
npm run docs:assemble
npm run dev
```

The development server is available at `http://localhost:4321` by default.

## Validation and production build

```bash
npm run validate
```

`npm run docs:assemble` exports the Griffe Python API and stages source-owned
Python and Studio content. `npm run check` performs Astro content and TypeScript
diagnostics. The static production site is written to `dist`. `npm run
validate:build` rejects broken internal build references and obsolete
source-repository URLs. It also proves migration-ledger routes, every contracted
Python API object and anchor, Pagefind output, and sitemap output. `npm run validate` runs
assembly, all site checks, and an idempotence check. `npm run preview` serves
the completed production build.

This component deliberately keeps its own `package-lock.json`; it is not part
of a repository-wide JavaScript workspace. CI installs each documentation
producer with its own lock and validates the complete source assembly without
retaining or deploying its generated output. Cloudflare Pages pulls pull-request
branches and `master`, runs `tooling/docs/build_cloudflare_pages.sh`, and
publishes them only as `next` preview deployments. Merging does not update
`junjo.ai`.

Production uses the dedicated `docs-production` source branch and the `stable`
channel. Python, Studio, and documentation-only release workflows validate the
stable source set, publish the GitHub release, and only then fast-forward that
branch to the exact release-tag commit. Cloudflare detects the ref update, pulls
the source, generates `apps/website/dist`, and updates `junjo.ai`. GitHub never
uploads or retains the generated site, and `dist` is never checked in.

`legacy-python-api/_redirects` is source configuration, not generated site
output. The `junjo-python-api` Cloudflare Pages project pulls that directory
from Git after the same approved merge. Its build waits for the unified Python
landing page to be live before publishing the single permanent redirect rule.
It must never be included in the `junjo.ai` output.

CI labels ordinary source builds as `next`. Stable assembly reads
`tooling/docs/stable-releases.json` so independently released Python and Studio
documentation cannot drift to unreleased `master` source. The channel, SDK
version, release tag, and full source revision are embedded in generated
manifests. Update the releasing component's manifest entry to its forthcoming
exact tag in the same release commit; documentation-only releases keep the
existing component selections.

## Content ownership

- `src/content/docs/index.mdx` owns the Starlight splash page at `/`.
- `src/content/docs` owns hand-authored platform pages.
- `src/content/docs/generated` is ignored, assembled output owned by its source
  components.
- `src/assets` owns source-controlled images processed by Astro.
- `public` owns files copied directly into the built site.

Keep product descriptions and repository links aligned with the current SDK,
Studio, and deployment surfaces in this monorepo. Do not duplicate or edit the
generated Python API reference here.

For equivalent multi-language tasks, use Starlight's `Tabs` and `TabItem` with
`syncKey="sdk-language"`. Add a language tab only after that SDK implements and
validates the documented behavior. API references always keep separate
language-specific routes.
