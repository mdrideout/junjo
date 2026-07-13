# Junjo Website AGENTS.md

This directory owns the independently built Astro/Starlight website published
at `junjo.ai`.

## Boundaries

- Own platform narrative, product pages, navigation, and concise platform
  guides here.
- Keep Python API and SDK implementation documentation canonical in
  `sdks/python/docs`; link to generated reference documentation instead of
  duplicating it.
- Do not import Studio frontend runtime code or merge this package into the
  Studio frontend dependency graph.
- Keep the website's `package.json` and `package-lock.json` independent. There
  is no root JavaScript workspace.
- Keep the static build deployable from this directory in isolation.

## Validation

Run from `apps/website`:

```bash
npm ci
npm run check
npm run build
npm audit --omit=dev --audit-level=high
```

The production artifact is `apps/website/dist`. Cloudflare Pages owns preview
and production deployment; GitHub Actions owns source validation.
