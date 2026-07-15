# ADR 0009: Unified documentation publishing

- Status: Accepted
- Date: 2026-07-14
- Amended: 2026-07-15 (production deployment and legacy-domain retirement)
- Owners: Junjo platform, SDKs, Studio, and website
- Supersedes: the documentation publishing and isolated website-build clauses
  of [ADR 0001](0001-junjo-platform-monorepo.md)

## Context

Junjo currently publishes a small Astro/Starlight website at `junjo.ai` and a
substantial Python Sphinx site at `python-api.junjo.ai`. The Sphinx source also
contains Studio, deployment, and observability material, while the website
contains only a small platform shell. This divides navigation and search and
puts product documentation under the Python SDK's publishing surface.

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
- A root documentation workflow stages the selected outputs, runs the normal
  website build, validates the complete artifact, and deploys that exact static
  artifact to Cloudflare Pages.
- Stable SDK reference pages describe installable releases and record the SDK
  version and source revision.
- Main-branch SDK output may be published only as an explicitly labeled `next`
  preview.
- Documentation deploys after the corresponding packages and Studio release.

The website's Node lock remains independent. Its renderer can still be
validated with already staged or fixture content, while the production portal
is proven by the cross-component assembly workflow.

### Migration

- Existing RST narrative content is converted mechanically to Markdown or MDX
  with section-level provenance and parity validation.
- Existing Python docstrings are parsed as Sphinx style during migration; a
  docstring-style rewrite is a separate decision.
- Sphinx remains warning-strict as a parity and rollback input until narrative,
  API, route, anchor, search, version, and release parity are verified.
- `python-api.junjo.ai` becomes the approved global retirement redirect only
  after the exact unified artifact passes its production build gates.
- Sphinx dependencies and sources are retired only in a later, explicit
  cutover after the roadmap's completion criteria are satisfied.

### Production Cutover Amendment (2026-07-15)

The owner approved the production cutover with two explicit changes to the
initial compatibility plan:

- GitHub Actions is the production builder and deployer. It assembles and
  validates one immutable `apps/website/dist` artifact, retains it, and direct
  uploads that exact artifact to the `junjo-website` Cloudflare Pages project.
  Cloudflare automatic Git builds are disabled at activation.
- The public Sphinx deployment is retired with one permanent global redirect:
  every request on `python-api.junjo.ai` returns a `301` to
  `https://junjo.ai/docs/python/`. Page-by-page route and fragment redirects are
  intentionally not part of the retirement surface.

This amendment supersedes the roadmap's original page-level compatibility and
parallel-publication requirements. It does not authorize deleting or rewriting
the migrated content. The route ledger, API baseline, Sphinx source, and final
Sphinx artifact remain as migration evidence and rollback inputs. Sphinx may
continue to run as a warning-strict parity check until a separate cleanup
removes that validation dependency.

## Consequences

Junjo gains one public navigation, search index, visual system, and domain
without merging product runtime dependencies. SDK releases gain deterministic,
versioned documentation artifacts. Documentation changes that cross ownership
boundaries require an integration build in addition to component validation.

The production website is no longer fully described by `apps/website` source
alone; it is a static assembly of explicitly versioned inputs. That added build
coordination is accepted because it prevents manually copied API reference and
keeps stable docs aligned with released packages.

The migration retains the Sphinx source and final static artifact as recovery
inputs, but only the unified Starlight site remains a public documentation
surface after cutover.

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
