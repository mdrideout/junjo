# Junjo website

This directory owns the public Junjo website at
[junjo.ai](https://junjo.ai/). It is an independent Astro and Starlight
application inside the Junjo platform repository.

The website explains how the platform components fit together. Detailed Python
SDK API and implementation documentation remains owned by `sdks/python/docs`
and is published at [python-api.junjo.ai](https://python-api.junjo.ai/). Studio
runtime code and deployment packages remain owned by `apps/studio`.

## Requirements

- Node.js 22.12 or newer
- npm 9.6.5 or newer

## Development

Run commands from `apps/website`:

```bash
npm ci
npm run dev
```

The development server is available at `http://localhost:4321` by default.

## Validation and production build

```bash
npm run check
npm run build
npm run validate:build
```

`npm run check` performs Astro content and TypeScript diagnostics. The static
production site is written to `dist`. `npm run validate:build` rejects broken
internal build references and obsolete source-repository URLs. `npm run
validate` runs all three required checks in sequence, and `npm run preview`
serves the completed production build locally.

This component deliberately keeps its own `package-lock.json`; it is not part
of a repository-wide JavaScript workspace. CI and deployment should install
with `npm ci` from this directory and publish only `apps/website/dist`.

## Content ownership

- `src/content/docs/index.mdx` owns the Starlight splash page at `/`.
- `src/content/docs` owns the remaining Starlight documentation pages.
- `src/assets` owns source-controlled images processed by Astro.
- `public` owns files copied directly into the built site.

Keep product descriptions and repository links aligned with the current SDK,
Studio, and deployment surfaces in this monorepo. Do not duplicate the Python
API reference here.
