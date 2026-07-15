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
source-repository URLs. It also proves migration-ledger routes, every Sphinx API
object and anchor, Pagefind output, and sitemap output. `npm run validate` runs
assembly, all site checks, and an idempotence check. `npm run preview` serves
the completed production build.

This component deliberately keeps its own `package-lock.json`; it is not part
of a repository-wide JavaScript workspace. CI installs each documentation
producer with its own lock, assembles one exact artifact, and publishes only
`apps/website/dist`. A second deployable directory,
`.docs-assembly/python-api-site`, contains the global permanent redirect used
to retire `python-api.junjo.ai`. It belongs only on the `junjo-python-api`
Cloudflare Pages project and must never be deployed on `junjo.ai`.

On a successful `master` build, GitHub Actions downloads the exact retained
artifacts and deploys `dist` to `junjo-website` before deploying the retirement
artifact to `junjo-python-api`. The `public-documentation-production` GitHub
environment owns the Cloudflare account ID and least-privilege Pages API token.
Cloudflare automatic Git deployments are disabled after direct upload is
activated; production is never rebuilt independently from source in two places.

CI labels ordinary source builds as `next`. A caller may request the `stable`
channel only from the exact released checkout; the channel, SDK version, and
full source revision are embedded in the generated pages and manifests.

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
