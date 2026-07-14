# Unified Documentation Portal Migration Strategy And Implementation Plan

- Status: Final strategy; implementation is gated on the required ADR approval
- Date: 2026-07-14
- Owners: Junjo platform, Python SDK, Studio, website, and future SDK owners
- Decision authority: accepted ADRs remain authoritative; approve the boundary
  changes described here before implementation

## Objective

Migrate Junjo's separately published Astro/Starlight website and Python Sphinx
documentation into one public Starlight documentation portal without losing,
silently shortening, or rewriting existing documentation.

This is a publishing and format migration. It is not an editorial rewrite.
Existing explanations, warnings, examples, API coverage, headings, images,
links, and useful historical routes remain accounted for throughout the
migration. Content may move to a more appropriate owner and RST markup may be
converted to Markdown or MDX, but the migration itself does not use that work as
an opportunity to replace the substance of the documentation.

The target combines two complementary presentation models:

- shared conceptual and task-oriented guides, with synchronized language tabs
  only when two SDKs implement the same behavior; and
- separately generated, language-specific API references with stable symbol
  links for Python and future TypeScript SDKs.

One public site does not create one documentation owner or one dependency
graph. Each SDK and product continues to own the content and generated
reference that describes its public contract. Starlight becomes the unified
renderer, navigator, search index, and deployment surface.

## Relationship To Accepted Architecture

[ADR 0001](../adr/0001-junjo-platform-monorepo.md) currently establishes that:

- `sdks/python` owns the Python SDK, its public API, examples, tests, package
  metadata, and Python documentation;
- `apps/website` owns the platform narrative, product pages, platform guides,
  and website deployment;
- the website may publish generated SDK reference output but may not create a
  second manually maintained Python API source of truth;
- deployables retain independent locks, builds, versions, and release
  artifacts; and
- the website must not become an SDK or Studio runtime dependency.

The target architecture preserves those runtime and source-ownership rules. It
does change the current documentation build and deployment boundary: the final
public artifact is assembled from outputs owned by more than one component.
Before implementation, update or supersede the relevant ADR text and scoped
`AGENTS.md` instructions to explicitly accept:

1. one public documentation deployment;
2. SDK-owned, versioned documentation export artifacts;
3. a cross-component documentation assembly workflow;
4. released-versus-next documentation behavior; and
5. the conditions under which Sphinx can be removed.

The ADR change precedes implementation. This roadmap does not silently redefine
an accepted architecture.

## Non-Negotiable Migration Invariants

### No Silent Content Deletion

Every existing documentation source must receive an explicit disposition in a
machine-readable migration ledger before it is moved or removed. The allowed
dispositions are:

- `migrated`: the content is published at a new Starlight route;
- `generated`: a hand-maintained reference surface is replaced by generated
  output whose symbol coverage is proven equivalent;
- `canonical-linked`: the content remains with its current owner and the public
  portal links to it instead of duplicating it;
- `corrected`: a demonstrably inaccurate statement or stale link is changed in
  a separately reviewable correction, with the old and new meaning recorded;
- `retired-placeholder`: non-product placeholder content is intentionally
  removed and recorded; or
- `retained`: the source remains unchanged because it is not part of the public
  documentation portal.

There is no generic `deleted`, `deduplicated`, or `cleaned up` disposition.
Duplicate material cannot disappear merely because another page discusses the
same subject. A merge requires section-level source-to-target mapping and human
review proving that all distinct guidance survived.

### Mechanical Conversion Before Editorial Change

RST-to-MDX work preserves wording, heading hierarchy, code, admonitions,
images, captions, cross-references, and examples as closely as the target
format permits. Mechanical markup changes and route changes belong in the
migration commit. Substantive wording changes belong in a separate commit or a
clearly separated review section.

Known stale content, such as obsolete repository links, must not be republished
as if it were correct. Correct only the inaccurate statement or link, record the
correction in the ledger, and do not rewrite the surrounding page under cover
of migration work.

### Source Ownership Is Preserved

- Python public docstrings, Python SDK guides, and generated Python API data
  remain owned by `sdks/python`.
- Future TypeScript comments, guides, examples, and TypeDoc configuration are
  owned by the TypeScript SDK.
- Platform narrative and cross-language concepts are owned by `apps/website`.
- Studio behavior and operator instructions remain owned by `apps/studio` and
  its deployment distributions.
- Accepted ADRs and implementation roadmaps remain in their current owners and
  are not turned into public product guides by this migration.

The public portal may render all of these outputs. It does not become their
canonical source.

### Releases, Not Main, Define Stable API Documentation

The stable public API reference must describe an installable SDK release. Main
branch documentation may be published as an explicitly labeled `next` preview,
but it must not silently replace the documentation for the latest released
package.

### Sphinx Remains Until Parity Is Proven

Sphinx remains buildable and deployable during migration. Its RST sources,
configuration, dependencies, generated site, and existing public domain are not
removed until all content, API, route, search, and release-parity gates in this
plan pass.

## Current Documentation Baseline

### Public Website

`apps/website` is an Astro/Starlight application deployed at `junjo.ai`. It
currently contains three content pages:

- `src/content/docs/index.mdx`;
- `src/content/docs/guides/example.md`; and
- `src/content/docs/reference/example.md`.

The homepage and example navigation are a small publishing shell rather than a
replacement for the existing SDK documentation. The homepage also contains
known stale product and repository references. These require narrowly scoped
accuracy corrections during migration.

The current website validation succeeds with:

```text
npm run check
npm run build
npm run validate:build
```

### Python Sphinx Site

`sdks/python/docs` contains 18 RST pages and 4,094 lines. It is currently the
substantial public documentation corpus for the Python SDK and also contains
Studio, Docker, deployment, and OpenTelemetry material.

The warning-strict Sphinx build currently succeeds. This successful build is
the functional baseline that the Starlight output must match before cutover.

Sphinx currently supplies more than page rendering:

- `autodoc` extraction;
- Sphinx-, Google-, and NumPy-style docstring support through Napoleon;
- class and `__init__` documentation;
- source-order members, undocumented members, and inheritance display;
- source-code views;
- intersphinx links;
- doctest and documentation-coverage extensions;
- general, module, and search indices;
- `objects.inv` for external object linking; and
- sitemap generation.

The migration must replace, intentionally retain, or explicitly retire each of
these behaviors. Removing the Sphinx HTML theme alone is not feature parity.

### Other Documentation Sources

The repository also contains public or operator-facing material in:

- `sdks/python/README.md`;
- `sdks/python/examples/**/README.md` and runnable example source;
- `apps/studio/README.md`;
- `apps/studio/deployments/minimal/README.md`;
- `apps/studio/deployments/vm-caddy/README.md`;
- `contracts/telemetry/README.md`;
- component ADRs; and
- root ADRs and roadmaps.

These sources are part of the content inventory even when they are not moved.
In particular, deployment distribution READMEs remain self-contained because
they are published into standalone operator-facing release mirrors. The public
site may link to or render selected exported material from them, but it must not
replace their release-owned instructions with a second hand-maintained copy.

## Target Documentation Architecture

```text
Python SDK source and docs
  -> Python-owned export command
  -> versioned MDX/API manifest artifact
                                      \
Future TypeScript SDK source and docs  \
  -> TypeScript-owned export command     -> Starlight assembly -> one static site
  -> versioned MDX/API manifest artifact /
                                       /
Platform and product content ----------
Studio-owned public/operator exports --
```

### Content Layers

| Layer | Canonical owner | Authoring model | Published presentation |
| --- | --- | --- | --- |
| Platform concepts | `apps/website` | Hand-authored MDX | Shared pages |
| Cross-language task guides | Platform prose plus SDK-owned examples | MDX with verified example imports | Synchronized language tabs when equivalent |
| Python guides | `sdks/python` | Migrated Markdown/MDX | Python section in Starlight |
| Python API | Python source, docstrings, and public export manifest | Griffe data plus an owned renderer | Generated symbol pages |
| TypeScript guides | Future TypeScript SDK | Markdown/MDX | TypeScript section in Starlight |
| TypeScript API | TypeScript source, comments, and package exports | TypeDoc data plus Starlight rendering | Generated symbol pages |
| Studio product docs | `apps/studio` or `apps/website`, as decided per page | MDX or exported Markdown | Studio section in Starlight |
| Deployment reference | Studio deployment distributions | Existing self-contained Markdown | Canonical source retained; portal links or renders owned export |

### Proposed Public Information Architecture

```text
/
/docs/
/docs/get-started/
/docs/concepts/
/docs/concepts/workflows/
/docs/concepts/agents/
/docs/guides/
/docs/observability/
/docs/studio/

/docs/python/
/docs/python/get-started/
/docs/python/guides/
/docs/python/api/
/docs/python/api/junjo/Workflow/

/docs/typescript/                 # added only when the SDK exists
/docs/typescript/get-started/
/docs/typescript/guides/
/docs/typescript/api/
```

The exact route spelling is approved in the documentation ADR and then treated
as a compatibility contract. API routes must use deterministic slugs derived
from fully qualified public symbol names, not display headings or unstable
generator defaults.

### Versioned Publishing

The production model is:

- `/docs/python/latest/...` resolves to the latest released documentation;
- `/docs/python/<version>/...` is immutable for retained versions;
- `/docs/python/next/...` may expose main-branch previews with an unmistakable
  unreleased banner; and
- concise unversioned routes may redirect to `latest`, but canonical links are
  version aware.

The same contract applies to future SDKs. Platform and Studio documentation can
remain unversioned where it describes the current deployed product, but every
generated SDK page must display its package version and source revision.

## Content Preservation Ledger

Before converting the first page, add a machine-readable ledger, for example
`tooling/docs/content-migration.json`. Each record must contain:

```json
{
  "source_path": "sdks/python/docs/getting_started.rst",
  "source_anchor": "getting_started",
  "source_hash": "sha256:...",
  "owner": "python",
  "disposition": "migrated",
  "target_route": "/docs/python/get-started/",
  "target_anchor": null,
  "code_blocks": [],
  "images": [],
  "outbound_links": [],
  "corrections": [],
  "status": "pending"
}
```

The ledger is generated initially, then reviewed and committed. Validation must
fail when:

- an RST page or section has no record;
- a code block, image, admonition, or named anchor is unmapped;
- a record marked `migrated` has no built target;
- a record marked `generated` loses a public symbol;
- a correction lacks a reason and review record; or
- a source is removed before its record reaches `verified`.

File hashes establish the baseline, but verification operates at section and
content-unit level so that intentional source changes do not make the ledger
useless.

### Sphinx Page Migration Matrix

The following matrix is the initial file-level ledger. Section-level entries
must be generated before implementation.

| Current source | Lines | Initial target | Migration treatment |
| --- | ---: | --- | --- |
| `index.rst` | 160 | `/docs/python/` | Preserve the complete Python landing content; do not collapse it into the marketing homepage |
| `getting_started.rst` | 145 | `/docs/python/get-started/` | Mechanical RST-to-MDX conversion |
| `tutorial.rst` | 162 | `/docs/python/tutorial/` | Mechanical conversion; preserve every tutorial step and code block |
| `agents.rst` | 163 | `/docs/python/agents/` | Mechanical conversion |
| `agent_testing.rst` | 79 | `/docs/python/agents/testing/` | Mechanical conversion |
| `agent_composition.rst` | 34 | `/docs/python/agents/composition/` | Mechanical conversion |
| `core_concepts.rst` | 294 | `/docs/python/concepts/` | Mechanical conversion; later cross-language extraction is separate work |
| `state_management.rst` | 125 | `/docs/python/workflows/state/` | Mechanical conversion |
| `concurrency.rst` | 182 | `/docs/python/workflows/concurrency/` | Mechanical conversion |
| `subflows.rst` | 247 | `/docs/python/workflows/subflows/` | Mechanical conversion |
| `hooks.rst` | 150 | `/docs/python/hooks/` | Mechanical conversion |
| `visualizing_workflows.rst` | 204 | `/docs/python/workflows/visualization/` | Preserve prose, Graphviz/Mermaid instructions, images, captions, and Agent distinction |
| `eval_driven_dev.rst` | 95 | `/docs/python/testing/eval-driven-development/` | Mechanical conversion |
| `api.rst` | 86 | `/docs/python/api/` and generated symbol routes | Preserve section introductions and explicit inclusion/exclusion policy; prove generated symbol parity |
| `junjo_ai_studio.rst` | 687 | `/docs/studio/overview/` or owned subpages | Rehome without rewriting; splitting requires section-level mappings |
| `docker_reference.rst` | 482 | `/docs/studio/docker-reference/` | Rehome without shortening; reconcile with canonical deployment READMEs explicitly |
| `deployment.rst` | 68 | `/docs/studio/deployment/` | Rehome without rewriting |
| `opentelemetry.rst` | 731 | `/docs/observability/opentelemetry/` | Rehome without shortening; retain all Python-specific examples during later language generalization |

Total baseline: 18 files and 4,094 lines. Line count is an inventory signal, not
the final parity measure. A format conversion may change line count while still
preserving every content unit.

### Website Content Matrix

| Current source | Disposition |
| --- | --- |
| `apps/website/src/content/docs/index.mdx` | Retain as the product landing source; correct obsolete links in separately identified corrections |
| `apps/website/src/content/docs/guides/example.md` | Record as a placeholder, retain until real navigation is live, then mark `retired-placeholder` |
| `apps/website/src/content/docs/reference/example.md` | Record as a placeholder, retain until generated reference is live, then mark `retired-placeholder` |

### README And Example Matrix

The detailed ledger must enumerate every heading and code block in the
following sources even when their disposition is `canonical-linked`:

| Source family | Required treatment |
| --- | --- |
| Python SDK README | Retain package landing and installation value; map any guide content reused by Starlight and prevent divergent manual copies |
| Python example READMEs and source | Retain runnable examples as canonical; link or import verified snippets instead of copying large blocks |
| Studio README | Retain contributor/operator onboarding; map public product guidance intentionally |
| Minimal deployment README | Retain as a self-contained released distribution document |
| VM/Caddy deployment README | Retain as a self-contained released distribution document |
| Telemetry contract README | Retain as the contract-owner reference; link from public observability material where useful |
| ADRs and roadmaps | Retain in place; they are architectural records, not migration fodder for product prose |

## Python API Reference Migration

### Canonical Inputs

The Python API reference is generated from:

1. package source and public docstrings;
2. root and subpackage `__all__` exports;
3. an explicit public module allowlist derived initially from `api.rst`; and
4. explicit exclusions that currently prevent duplicate or misleading entries.

The initial allowlist contains these 12 current `automodule` targets:

```text
junjo
junjo.agent.definition
junjo.agent.model_driver
junjo.agent.tool
junjo.agent.messages
junjo.agent.result
junjo.agent.state
junjo.agent.json
junjo.agent.errors
junjo.agent.testing
junjo.hooks
junjo.telemetry.junjo_otel_exporter
```

Do not recursively publish every class or function Griffe discovers. Private
runtime objects are not public merely because static analysis can see them.

### Griffe Contract

Griffe is the Python extractor and docstring parser. Junjo owns the thin,
deterministic renderer from Griffe's model into Starlight-compatible MDX and a
symbol manifest. Do not make an unproven third-party MDX theme or generator the
only representation of the public API contract.

The migration initially configures the Sphinx docstring parser explicitly. It
must support the repository's current:

- `:param:` and `:type:` fields;
- returns, return types, and raised exceptions;
- Sphinx roles such as `:class:` and `:meth:`;
- code-block and note directives inside docstring bodies;
- class and rich `__init__` documentation;
- source ordering;
- inherited-member presentation;
- undocumented public members; and
- source links pinned to the documented release tag or revision.

Converting the public docstring standard to Google style is not part of this
migration. Griffe can support that style later, but a style change requires its
own decision, complete conversion plan, editor-hover review, and validation.
There must not be a mixed accidental style transition hidden inside renderer
work.

### Generated Output Contract

The Python exporter produces:

- one index and deterministic pages for public modules and symbols;
- MDX containing signatures, documentation sections, examples, admonitions,
  and source links;
- `api-manifest.json` containing fully qualified names, kinds, routes, anchors,
  aliases, and source locations;
- a public-symbol inventory used for parity comparison;
- a redirects/legacy-anchor manifest; and
- version and source-revision metadata.

Generated files are build artifacts. They are written to an ignored staging
directory or uploaded as versioned CI artifacts; they are not hand-edited.

### API Parity Gates

The generated API cannot replace Sphinx until:

- every current Sphinx public symbol appears in the Griffe manifest or has an
  approved exclusion record;
- every package export intended to be public is documented;
- no private symbol is exposed accidentally;
- function and method signatures match the documented release;
- class and `__init__` content both render where Sphinx currently combines them;
- current warnings, examples, parameter descriptions, returns, and exceptions
  render without semantic loss;
- cross-references resolve;
- each page provides an exact-tag or exact-revision source link;
- API pages appear in Starlight/Pagefind search and the sitemap; and
- generation is deterministic and leaves the repository clean.

## Cross-Language Guides And Code Tabs

Language tabs and generated API reference solve different problems and are both
required.

Use synchronized `Python` and `TypeScript` tabs only when:

- both SDKs implement the same documented semantic contract;
- each example is supported and tested;
- shared prose remains truthful for both implementations; and
- the tab does not obscure a meaningful language-specific difference.

If only Python exists, preserve the Python example as ordinary Python content.
Do not add empty TypeScript tabs or speculative TypeScript code. If APIs differ
substantially, use separate language-specific guide pages and a visible support
matrix.

Existing Python examples are migrated intact. Later TypeScript examples are
additions, not replacements. Prefer importing or extracting examples from
SDK-owned, runnable files. Where an existing RST page contains an inline code
block, first migrate the block unchanged; extracting it into a tested example
is a separate improvement with its own review.

API references are never combined into tabbed symbol pages. Python and
TypeScript symbols require separate stable routes for search, IDE links,
support responses, and versioning.

## Build, CI, And Deployment Contract

### Component-Owned Export Commands

Each SDK owns a deterministic documentation command that runs in that SDK's
native environment and lockfile. Conceptually:

```text
sdks/python:     docs-export --version <version> --output <artifact>
sdks/typescript: docs-export --version <version> --output <artifact>
```

The Starlight package does not import SDK runtime code or add Python packages to
its Node dependency graph. A root documentation workflow orchestrates component
commands and stages their output before the normal website build.

### Recommended Production Pipeline

Use GitHub Actions to assemble and validate the exact static production
artifact, then deploy that artifact to Cloudflare Pages. Do not let an opaque
Cloudflare build independently regenerate API documentation from whatever main
branch happens to contain.

The production sequence is:

1. obtain the selected released SDK documentation artifacts;
2. stage platform, Studio, and SDK content into an ignored assembly tree;
3. run Starlight content and TypeScript checks;
4. build the static site;
5. validate links, routes, anchors, symbol manifests, search, sitemap, and
   version metadata;
6. retain the deployable artifact for rollback; and
7. deploy documentation last, after the corresponding packages and Studio
   release are public.

For pull requests, a cross-component public-docs workflow builds `next` output
from the changed source tree. It is triggered by:

- website content or configuration changes;
- Python public source, docstrings, docs, examples, or export-tool changes;
- Studio public docs or deployment documentation changes;
- telemetry public documentation changes;
- future TypeScript public source, docs, examples, or export-tool changes; and
- documentation workflow or assembly changes.

Existing component validation remains required. A successful Starlight build
does not replace Python tests, type checking, package validation, Studio tests,
deployment validation, or telemetry conformance.

### Required Documentation Gates

The integrated workflow must check:

- warning-free component documentation export;
- deterministic generated output;
- a clean working tree after generation;
- complete content-ledger coverage;
- exact public API symbol-set parity;
- no undocumented removal relative to the approved baseline;
- valid internal links and asset references;
- valid legacy routes and anchor aliases;
- searchable generated API pages;
- sitemap and canonical URL correctness;
- displayed SDK version and revision correctness;
- runnable or compile-checked code examples where tooling exists;
- accessible headings, tabs, admonitions, tables, images, and alt text; and
- successful production Starlight build.

A scheduled external-link check should report third-party link decay without
making unrelated release builds nondeterministic.

## Legacy URL And Anchor Preservation

Before moving pages, crawl and record all existing production Sphinx routes,
including `.html`, extensionless Cloudflare variants, named document anchors,
and API symbol fragments.

The redirect manifest maps at least:

```text
https://python-api.junjo.ai/getting_started.html
https://python-api.junjo.ai/getting_started
https://python-api.junjo.ai/api.html
https://python-api.junjo.ai/api
https://python-api.junjo.ai/api.html#junjo.Workflow
```

to their new routes or compatibility pages.

HTTP redirect handlers do not receive URL fragments. Therefore old Sphinx API
anchors cannot be preserved by server redirects alone when the target symbol
slug changes. Use one or both of:

- legacy anchor aliases embedded in compatibility pages; and
- a small, tested client-side fragment mapper on the legacy API landing route.

Keep `python-api.junjo.ai` as a redirecting compatibility domain through at
least the agreed support window. Do not merely turn off the Sphinx deployment.
Monitor production 404s and unresolved legacy fragments during the parallel
and post-cutover periods.

## Implementation Work Packages

### Work Package 0: Decision And Immutable Baselines

Tasks:

- approve the documentation architecture ADR change;
- update scoped ownership and validation instructions;
- record the Sphinx and Starlight build commands and versions;
- crawl the production Sphinx and website routes;
- generate file-, section-, code-, image-, link-, and anchor-level inventories;
- snapshot the current Sphinx public symbol inventory;
- create the machine-readable content and redirect ledgers; and
- render and retain representative baseline screenshots for visual comparison.

Exit gate:

- every current documentation source has an owner and planned disposition;
- all 18 RST files and all current website pages are represented;
- all public Sphinx symbols and legacy routes are captured; and
- both existing builds remain green.

No source content moves in this work package.

### Work Package 1: Starlight Portal And Assembly Foundation

Tasks:

- establish the approved navigation and route hierarchy;
- add generated-content staging that remains outside hand-authored source;
- add version and source-revision metadata support;
- add synchronized language-tab conventions;
- add unified search and sitemap expectations;
- implement the cross-component preview build; and
- correct narrowly identified stale homepage links without rewriting the page.

Exit gate:

- the Starlight shell builds locally and in CI with representative staged
  content;
- component dependency graphs remain independent; and
- no Sphinx page or production route has been removed.

### Work Package 2: Griffe Proof Of Concept

Generate a representative API slice containing at least:

- `Workflow`;
- `Graph`;
- `Node`;
- `Agent`; and
- one hooks or telemetry surface.

The slice must exercise rich `__init__` documentation, inheritance, parameter
and exception sections, Sphinx roles, examples, source links, exclusions, and
legacy anchors.

Exit gate:

- the generated slice matches the Sphinx meaning and public signatures;
- renderer snapshots and symbol manifests are deterministic;
- no private objects leak; and
- the approach is approved before full generation work begins.

### Work Package 3: Complete Python API Export

Tasks:

- implement all 12 current module targets;
- derive and validate public symbols from exports and the allowlist;
- render complete module and symbol pages;
- generate versioned API, route, source-link, and legacy-anchor manifests;
- index the reference in Starlight search and sitemap; and
- diff generated coverage against the Sphinx baseline in CI.

Exit gate:

- all API parity gates pass with zero unexplained additions or removals;
- existing Sphinx remains published; and
- reviewers approve the generated reference for full migration use.

### Work Package 4: Page-By-Page Narrative Migration

Migrate one RST page at a time according to the matrix. For each page:

1. freeze or refresh its section-level baseline;
2. convert RST syntax mechanically;
3. preserve text, headings, code, admonitions, images, captions, and links;
4. add provenance metadata pointing to the source page and revision;
5. render both old and new pages;
6. review the content-unit diff and visual comparison;
7. validate code and links;
8. add route and anchor compatibility; and
9. mark the ledger record `verified` only after human approval.

Begin with smaller Python pages, then tutorial and core guides, then the large
Studio and OpenTelemetry pages. Splitting a large page is allowed only when
every original section maps to a target page and the combined target content is
reviewed against the original.

Exit gate:

- all 4,094 baseline RST lines are represented by verified content units or
  separately recorded corrections;
- no code block, image, warning, link, or named anchor is unmapped; and
- the Starlight corpus passes its full build and content checks.

### Work Package 5: Ownership Reconciliation Without Duplication

Tasks:

- place migrated Python guides under Python ownership even though Starlight
  publishes them;
- move Studio-specific source mechanically to an approved Studio-owned public
  docs location where appropriate;
- preserve deployment READMEs as self-contained release artifacts;
- replace any portal copies of operator instructions with owned exports or
  explicit canonical links; and
- record overlap between READMEs and portal pages without deleting unique
  guidance.

Exit gate:

- every published page has exactly one canonical source owner;
- no generated or copied content is hand-edited in the portal; and
- standalone deployment distributions remain complete.

### Work Package 6: Release Integration And Parallel Production

Tasks:

- produce versioned docs artifacts with SDK releases;
- assemble stable production docs from released artifacts;
- publish an optional clearly labeled `next` preview;
- deploy the unified site without changing the old Sphinx domain;
- run production route, fragment, search, sitemap, canonical, and version
  checks; and
- observe both sites through an agreed parallel validation window.

Exit gate:

- the unified site describes installable released components;
- every legacy route resolves correctly;
- production monitoring shows no unexplained content or link regressions; and
- the retained static artifact can be redeployed as a rollback.

### Work Package 7: Cutover And Sphinx Retirement

Tasks:

- redirect `python-api.junjo.ai` through the tested compatibility mapping;
- update PyPI metadata, repository READMEs, website links, sitemaps, and
  canonical URLs;
- retain the final Sphinx artifact for rollback and historical comparison;
- remove Sphinx only from active generation after all completion criteria pass;
- update Python validation and release policy to use the new export and unified
  build; and
- record the final migration outcome and any explicitly retired behavior.

Exit gate:

- the support window completes without unresolved regressions;
- no source or content-ledger record remains pending;
- there is no second manually maintained API reference; and
- the old Sphinx deployment can be retired without losing a public route,
  symbol, or useful document.

### Work Package 8: Future TypeScript SDK Integration

This work begins only when a real TypeScript SDK and public export surface
exist.

Tasks:

- add TypeDoc using package exports as the public boundary;
- emit the same language-neutral documentation artifact contract;
- add TypeScript routes without changing Python routes;
- introduce verified Python/TypeScript tabs for equivalent guides;
- show explicit feature-support differences; and
- compile-check every published TypeScript example.

TypeScript integration extends the portal. It does not rewrite or generalize
away the already migrated Python content.

## Validation And Review Matrix

| Concern | Required evidence |
| --- | --- |
| Content preservation | Section-level ledger has no unmapped source units |
| API preservation | Sphinx and Griffe public-symbol inventories match, except approved records |
| Wording preservation | Mechanical conversion diff and human review per page |
| Code preservation | Every original block mapped; runnable examples tested where possible |
| Images | Every source image, caption, alt text, and target asset validated |
| Links | Internal links, target routes, legacy routes, and scheduled external links checked |
| Anchors | Named RST anchors and Sphinx symbol fragments mapped and tested |
| Search | Guides and generated symbol pages present in Pagefind results |
| Version correctness | Displayed SDK version and source revision match released artifact |
| Accessibility | Heading order, tabs, tables, admonitions, images, and keyboard behavior reviewed |
| Visual parity | Representative old/new rendered pages compared before approval |
| Build isolation | SDK generators use SDK locks; Starlight uses the website lock |
| Release rollback | Previous static artifact and final Sphinx artifact remain deployable |

## Rollback Strategy

Every production documentation deployment retains its complete static artifact
and input manifests. During parallel publication:

- the existing Sphinx site remains deployable;
- DNS and compatibility redirects remain independently reversible;
- the unified site can roll back to its previous static artifact without
  rebuilding SDK docs;
- generated documentation artifacts remain immutable; and
- content ledgers identify exactly which source revision produced each route.

A documentation problem does not trigger a package rollback unless the package
itself is incorrect. Restore the prior documentation artifact, correct the
source or generator, rerun parity checks, and deploy a new documentation
artifact.

## Explicitly Outside This Migration

The following are not authorized as incidental migration work:

- shortening or modernizing prose for style;
- merging pages merely to reduce page count;
- deleting duplicate-looking guidance without a content-unit comparison;
- changing Python runtime APIs;
- changing telemetry or Studio behavior;
- converting all docstrings from Sphinx to Google style;
- inventing TypeScript APIs or examples before the SDK exists;
- replacing self-contained deployment README content with website-only docs;
- changing product terminology except through separately approved corrections;
  or
- adopting an unrelated documentation framework or hosted documentation
  platform.

Improvements discovered during migration should be recorded as follow-up work.
They do not block faithful transfer unless the existing content is factually
unsafe or prevents the target build from functioning.

## Completion Criteria

The migration is complete only when all of the following are true:

- the architecture and build-boundary ADR change is accepted;
- every current documentation source has an approved final disposition;
- all 18 Sphinx pages and all 4,094 baseline lines have section-level coverage;
- every original code block, image, caption, admonition, link, and named anchor
  is mapped;
- every intended public Python symbol is generated and no private symbol leaks;
- the current stable docs identify an installable SDK version and exact source
  revision;
- Starlight search, sitemap, internal links, canonical URLs, and accessibility
  validation pass;
- all legacy pages and API deep links resolve through preserved anchors or
  tested compatibility mappings;
- deployment distributions remain self-contained;
- production has completed the agreed parallel validation and rollback window;
- the Python release policy and CI use the new documentation export contract;
- no hand-maintained duplicate API reference exists; and
- the final migration record lists every correction and intentionally retired
  placeholder or Sphinx-only feature.

Until every criterion passes, the work remains a migration in progress and the
Sphinx sources and rollback artifact remain authoritative recovery inputs.
