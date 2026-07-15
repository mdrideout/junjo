# Junjo Website AGENTS.md

This directory owns the independently locked Astro/Starlight renderer published
at `junjo.ai`. The production portal is assembled from source-owned platform,
SDK, and Studio documentation according to ADR 0009.

## Boundaries

- Own platform narrative, product pages, navigation, and concise platform
  guides here.
- Keep Python API and SDK implementation documentation canonical in
  `sdks/python/docs`; stage its Griffe-generated output instead of duplicating
  or editing it here.
- Do not import Studio frontend runtime code or merge this package into the
  Studio frontend dependency graph.
- Keep the website's `package.json` and `package-lock.json` independent. There
  is no root JavaScript workspace.
- Keep the Node renderer independently locked and buildable with already staged
  or fixture documentation content. The complete production artifact is owned
  by the root cross-component documentation assembly workflow.

## Validation

After the root documentation assembly, run from `apps/website`:

```bash
npm ci
npm run check
npm run build
npm run validate:build
npm audit --omit=dev --audit-level=high
```

The production artifact is `apps/website/dist`. GitHub Actions assembles and
validates source without retaining or deploying an artifact. Cloudflare Pages
pulls pull-request branches and `master` as `next` previews. Only a successful
published-release workflow may fast-forward `docs-production`; Cloudflare pulls
that branch, repeats the version-controlled build as `stable`, and deploys its
own generated output to `junjo.ai`.
