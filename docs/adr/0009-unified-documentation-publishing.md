# ADR 0009: Unified documentation publishing

- Status: Accepted
- Date: 2026-07-14
- Amended: 2026-07-15 (release-gated production, legacy-domain retirement, and
  current-source Sphinx retirement)
- Owners: Junjo platform, SDKs, Studio, and website
- Supersedes: the documentation publishing and isolated website-build clauses
  of [ADR 0001](0001-junjo-platform-monorepo.md)

## Context

Before this decision, Junjo published a small Astro/Starlight website at
`junjo.ai` and a substantial Python Sphinx site at `python-api.junjo.ai`. The
legacy source also contained Studio, deployment, and observability material,
while the website contained only a small platform shell. That divided
navigation and search and put product documentation under the Python SDK's
publishing surface.

Future language SDKs need one discoverable documentation portal without
sharing runtime dependency graphs or creating manually maintained copies of
their API references. The migration must preserve the complete existing
documentation corpus, public API coverage, examples, assets, URLs, and useful
deep links. It is not an editorial rewrite.

The full preservation, sequencing, and validation contract is recorded in
[Unified Documentation Portal Migration Strategy And Implementation Plan](../roadmaps/UNIFIED_DOCUMENTATION_MIGRATION.md).

## Decision

Junjo publishes one public Astro/Starlight documentation portal at `junjo.ai`.
The portal combines source-owned documentation exports into one static artifact.

### Ownership

- `apps/website` owns the Starlight renderer, navigation, search, platform
  narrative, cross-language guides, and final static artifact.
- Each SDK owns its language-specific guides, examples, public export boundary,
  docstrings or source comments, documentation generator, and versioned
  documentation artifact.
- `apps/studio` owns Studio behavior and operator documentation. Standalone
  deployment README files remain complete release-owned artifacts.
- The portal stages owned outputs. Generated or copied outputs are never edited
  as second sources of truth.

This is a build-time publishing relationship. The website is not an SDK or
Studio runtime dependency, and no component imports another product's runtime
code to generate documentation.

### Presentation

- Platform concepts and genuinely equivalent tasks use shared prose.
- Synchronized language tabs are used only when each displayed SDK implements
  and validates the same behavior.
- API references remain language-specific, generated, versioned, searchable,
  and deep-linkable.
- Python API extraction uses Griffe, the explicit public exports, and an owned
  deterministic Starlight renderer.
- A future TypeScript SDK uses TypeDoc and its package exports under the same
  documentation artifact contract.

### Assembly And Release

- Component-owned export commands run with their own locks and native tools.
- A version-controlled root documentation command stages the selected outputs,
  runs the normal website build, and validates the complete artifact.
- GitHub Actions runs that contract as source validation, then discards its
  generated output. It does not persist or deploy documentation artifacts.
  Cloudflare Pages pulls and builds source for every same-repository pull-request
  branch and for `master` as preview deployments. Those preview builds use the
  explicitly labeled `next` channel and never update `junjo.ai`.
- The Cloudflare production branch is `docs-production`. A release workflow may
  fast-forward that branch to the exact release-tag commit only after all release
  gates succeed and the GitHub release is published. Cloudflare then pulls that
  source, builds it with the `stable` channel, and updates `junjo.ai`. Generated
  `apps/website/dist` output is never checked in, uploaded by GitHub, or passed to
  Cloudflare.
- Stable SDK reference pages describe installable releases and record the SDK
  version and source revision.
- A source-owned stable-release manifest pins each independently released SDK or
  product documentation input. A component release must select its own exact tag;
  a documentation-only release retains the existing component selections.
- Main-branch SDK output may be published only as an explicitly labeled `next`
  preview.
- Documentation deploys after the corresponding packages and Studio release.

The website's Node lock remains independent. Its renderer can still be
validated with already staged or fixture content, while the production portal
is proven by the cross-component assembly workflow.

### Migration

- Existing RST narrative content is converted mechanically to Markdown or MDX
  with section-level provenance and parity validation.
- Existing reST field-list docstrings are parsed directly by Griffe; a
  docstring-style rewrite is a separate decision.
- The warning-strict legacy renderer remains historical parity evidence only;
  it is not part of current-source validation or publication.
- `python-api.junjo.ai` becomes the approved global retirement redirect only
  after the unified Cloudflare source build passes its production gates.
- Renderer dependencies and current RST sources are retired after the roadmap's
  completion criteria are satisfied.

### Initial Production Cutover Amendment (2026-07-15)

The owner approved the production cutover with two explicit changes to the
initial compatibility plan:

- Cloudflare Pages remains the production builder and deployer through its Git
  integration. The `junjo-website` project pulls the protected `master` commit
  and runs the version-controlled `tooling/docs/build_cloudflare_pages.sh`
  contract. GitHub Actions independently validates the pull-request source but
  neither persists nor deploys its output. Generated `dist` output is never
  checked in.
- The public Sphinx deployment is retired with one permanent global redirect:
  every request on `python-api.junjo.ai` returns a `301` to
  `https://junjo.ai/docs/python/`. Page-by-page route and fragment redirects are
  intentionally not part of the retirement surface.

This amendment supersedes the roadmap's original page-level compatibility and
parallel-publication requirements. It does not authorize deleting or rewriting
the migrated content. The route ledger, immutable public-surface snapshots,
repository history, and final legacy artifact remain migration evidence and
rollback inputs.

### Release-Gated Production Amendment (2026-07-15)

The owner subsequently separated preview publication from production promotion:

- `master` is no longer a production signal and must not be merge-blocked for the
  purpose of website deployment. GitHub validation remains visible on pull
  requests and pushes, but repository releases retain the publication gates.
- `docs-production` is a monotonic source pointer, not an authored branch. It is
  initialized at the existing production commit and may advance only by
  fast-forward to a published `sdk-python-v*`, `studio-v*`, or
  `docs-release-YYYYMMDD.N` tag that is reachable from `master`.
- Python and Studio release workflows validate the stable documentation set as
  part of their release transaction and promote only after their existing
  package or product publication succeeds. A documentation-only release runs the
  same stable validation before promotion.
- Cloudflare's Git integration owns every build and deployment. Production and
  preview environment variables select `stable` and `next` respectively, and the
  source-build contract fails closed if Cloudflare routes those channels to the
  wrong branch.

This amendment supersedes only the initial cutover's protected-`master`
production signal. The source-build ownership, no-artifact rule, unified portal,
content-preservation contract, and global legacy-domain redirect remain unchanged.

### Current-Source Sphinx Retirement Amendment (2026-07-15)

After the unified portal, global redirect, route parity, generated API parity,
search, sitemap, and deterministic source builds were verified, the owner
explicitly approved final cleanup:

- current RST pages, renderer configuration, themes, and Python dependencies
  are removed;
- Python narrative documentation under `sdks/python/docs/content` becomes the
  canonical owned Markdown source;
- `api-public-surface.json` becomes the explicit Griffe publication contract,
  replacing the renderer-generated inventory as an active input;
- the pinned Python 0.64.0 stable selection uses a reviewed immutable
  public-surface snapshot and an isolated RST-to-Markdown converter, so it can
  still be published without installing or running Sphinx; and
- the legacy Cloudflare Pages project remains intentionally active only as the
  permanent global redirect. The final rendered legacy deployment remains in
  Cloudflare history for rollback.

This amendment completes the planned renderer retirement without deleting or
rewriting migrated content.

## Consequences

Junjo gains one public navigation, search index, visual system, and domain
without merging product runtime dependencies. SDK releases gain deterministic,
versioned documentation artifacts. Documentation changes that cross ownership
boundaries require an integration build in addition to component validation.

The production website is no longer fully described by `apps/website` source
alone; it is a static assembly of explicitly versioned inputs. That added build
coordination is accepted because it prevents manually copied API reference and
keeps stable docs aligned with released packages.

Repository history and the final static legacy artifact remain recovery inputs,
but only the unified Starlight site is a public documentation surface after
cutover.

## Rejected Alternatives

### Keep Separate Public Sites

Rejected because users would continue to navigate separate search, hierarchy,
and visual systems, and every future SDK would add another public island.

### Move All Documentation Source Into The Website

Rejected because it would make the renderer a second source of truth for SDK
and Studio contracts and would blur release ownership.

### Use Language Tabs For API Reference

Rejected because symbols require independent language, version, search, IDE,
and support links.

### Rewrite Documentation During Migration

Rejected because simultaneous format, ownership, route, and editorial changes
would make content loss difficult to detect. Improvements are reviewed after
faithful migration or as explicitly recorded corrections.
