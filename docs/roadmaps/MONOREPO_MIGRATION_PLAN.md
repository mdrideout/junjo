# Junjo Platform Monorepo Migration Plan

## Status

Source consolidation and repository remediation are complete. Pull request 12
merged with history preserved at
`02f34073ceb40963e716498cf2caaaddafa2db28` on 2026-07-13.

- The Python SDK and Junjo AI Studio source migration was completed on the
  `codex/platform-monorepo-migration` branch on 2026-07-12.
- The website and both Studio deployment distributions were imported with
  their preserved histories on the same migration branch.
- The prepared branch change contains the accepted Apache-2.0 boundary, Junjo-owned Studio
  UI foundation, CI, deterministic exports, exact release transaction, mirror
  publication, setup-wizard proof, and end-to-end deployment telemetry smoke.
- Exact revisions, tree identities, and repository validation results are
  recorded in `MONOREPO_MIGRATION_RECORD.md`.
- Tag-restricted GitHub environments and base branch protection are configured;
  repository validation passed on the final revision. Credentials, action-SHA
  enforcement, the immutable release-tag ruleset, Cloudflare, PyPI, production
  mirrors, and repository retirement remain the external cutover described by
  `MONOREPO_GITHUB_CUTOVER_RUNBOOK.md`.

The implemented fixes and remaining completion gates are defined in
`MONOREPO_MIGRATION_REMEDIATION_PLAN.md`. Historical Catalyst use is resolved
by the license holder's confirmed Tailwind UI/Plus purchase and application
end-product use. Pull-request validation is complete. Credentials,
publishing, hosting, and old-repository retirement remain explicit cutover
work. The Python docs Cloudflare project is edited in place; the website Pages
project is deleted/recreated because Cloudflare cannot change the repository of
an existing Git-integrated project.

ADR 0001 defines the accepted end state. This plan records how the repository
was moved to that state without mixing runtime refactors into the structural
work, and identifies the remaining external cutover boundary.

The executable GitHub Actions, environments, credentials, publishing, hosting,
external-repository, verification, and forward-recovery procedure is defined in
`MONOREPO_GITHUB_CUTOVER_RUNBOOK.md`.

## Objective

Make the `junjo` repository the canonical source and integration boundary for:

- current and future Junjo SDKs;
- Junjo AI Studio;
- shared telemetry contracts;
- the Junjo website;
- supported Studio deployment distributions;
- platform ADRs, roadmaps, validation, and release routing.

The migration must preserve simple ownership boundaries. One repository does
not mean one package, dependency graph, lock, runtime, version, or deployment.

## Decisions Already Made

The following are not open migration questions:

1. The existing `junjo` repository remains the destination.
2. The Python SDK remains in `sdks/python`.
3. Studio remains in `apps/studio`.
4. The website moves to `apps/website`.
5. The minimal Studio distribution moves to
   `apps/studio/deployments/minimal`.
6. The VM/Caddy deployment example moves to
   `apps/studio/deployments/vm-caddy`.
7. The deployment repositories remain available as one-way generated
   distributions, not co-equal editable sources.
8. The old website repository is archived after hosting and source cutover.
9. All Junjo-authored components use Apache License 2.0.
10. `.env.bak` and interrupted atomic-writer staging files are secret-bearing
    local state and must be ignored and excluded from imports and
    distributions.
11. Useful Git history is preserved through rehearsed imports.
12. Independently deployable products keep separate locks, builds, validation,
    and releases; deployment distributions release with Studio.

## Target Repository Shape

```text
junjo/
├── AGENTS.md
├── README.md
├── LICENSE                              # Apache-2.0
├── sdks/
│   ├── python/
│   │   ├── AGENTS.md
│   │   ├── LICENSE                      # Apache-2.0
│   │   ├── pyproject.toml
│   │   ├── uv.lock
│   │   ├── src/junjo/
│   │   ├── tests/
│   │   ├── docs/
│   │   └── examples/
│   └── <future-language>/
├── apps/
│   ├── studio/
│   │   ├── AGENTS.md
│   │   ├── LICENSE                      # Apache-2.0
│   │   ├── VERSION
│   │   ├── backend/
│   │   ├── frontend/
│   │   ├── ingestion/
│   │   ├── proto/
│   │   ├── docs/
│   │   ├── scripts/
│   │   └── deployments/
│   │       ├── minimal/
│   │       │   ├── LICENSE              # included in exported artifact
│   │       │   ├── README.md
│   │       │   ├── docker-compose.yml
│   │       │   ├── .env.example
│   │       │   ├── scripts/junjo
│   │       │   └── examples/
│   │       └── vm-caddy/
│   │           ├── LICENSE              # included in exported artifact
│   │           ├── README.md
│   │           ├── docker-compose.yml
│   │           ├── .env.example
│   │           ├── scripts/junjo
│   │           ├── caddy/
│   │           └── junjo_app/
│   └── website/
│       ├── AGENTS.md
│       ├── LICENSE                      # Apache-2.0
│       ├── README.md
│       ├── package.json
│       ├── package-lock.json
│       ├── astro.config.mjs
│       ├── public/
│       └── src/
├── contracts/
│   └── telemetry/
├── docs/
│   ├── adr/
│   └── roadmaps/
├── tooling/
└── .github/workflows/
```

## Ownership Boundaries

### Python SDK

`sdks/python` owns the Python public API, runtime, tests, examples, package
metadata, Sphinx documentation, and PyPI release.

### Studio

`apps/studio` owns the backend, frontend, ingestion service, internal RPC
contracts, Studio version, Docker images, and supported operator deployment
distributions.

The source-development Compose configuration remains separate from deployment
Compose files that consume prebuilt production images. One file must not be
forced to serve both concerns.

### Website

`apps/website` owns the product site, platform narrative, platform-level guides,
navigation, and its static-site deployment.

Python API and SDK documentation remains canonical in `sdks/python/docs`. The
website may link to or publish generated SDK reference output but must not
maintain competing hand-written Python API documentation.

### Deployment distributions

The deployment directories are Studio-owned release surfaces. Their external
repositories are distribution channels optimized for `git clone`, not source
ownership boundaries.

### Shared contracts

`contracts/telemetry` owns cross-language schemas, versions, canonical fixtures,
and producer/consumer expectations. It contains no Studio or SDK business
logic.

## Reviewed Pre-Import Source Baselines

The baselines originally reviewed for planning were:

| Component | Reviewed source tip | Important state |
|---|---|---|
| Existing monorepo | current migration branch | SDK and Studio already imported |
| Website | `ce1a597caceddc19362181c4c96ae48a5611da7d` | local checkout has uncommitted redesign work |
| Minimal deployment | `e135323140d880b783a12cd28690d7bbd04b9594` | clean; pins Studio 0.81.1 |
| VM/Caddy deployment | `a6b6bade3dfdfc9ff5ce451df5136ba290562f74` | clean; pins Studio 0.81.1 and SDK 0.63.0 |

Before implementation, each source was preserved on
`codex/monorepo-source-prep`, then imported from a disposable clean clone. The
prepared revisions and rewritten import revisions superseding these reviewed
baselines are recorded in `MONOREPO_MIGRATION_RECORD.md`.

## Licensing Plan

All Junjo-authored source and published distributions will use Apache License
2.0.

Implementation work includes:

- verify that Junjo has the rights needed to relicense all Junjo-owned source
  and resolve any contributor-specific grants before publication;
- replace `apps/studio/LICENSE` with Apache-2.0;
- replace AGPL language in the Studio README and any owned metadata;
- search source, docs, container labels, package manifests, generated archives,
  and website notices for obsolete AGPL declarations;
- add Apache-2.0 component licenses where independently packaged artifacts need
  to remain self-describing;
- ensure both deployment export roots contain `LICENSE`;
- ensure website source and assets have an explicit Apache-2.0 disposition;
- retain required third-party notices and dependency licenses;
- update the default branches of surviving distribution and archived source
  repositories so they do not advertise a conflicting current license;
- update root documentation only in the same implementation commit that makes
  the repository license state true.

The license change is a deliberate product decision, not an incidental result
of moving files beneath the root license. Validation must fail if Junjo-owned
AGPL declarations remain in current trees, published artifacts, or external
default branches after relicensing. Historical commits retain their historically
accurate license files; do not rewrite published history merely to change old
license text.

## Secret And Local-State Protection

The current Studio setup wizard and both deployment setup wizards can create
`.env.bak`. A backup may contain the same production secrets as `.env`. The
existing root `env.bak/` pattern does not match the `.env.bak` file and is not
adequate protection.

Before history import or distribution publication:

- add `.env.bak` to the applicable Studio and deployment `.gitignore` files;
- retain `.env` and runtime data ignores;
- add a test or archive assertion proving neither `.env` nor `.env.bak` can be
  included in an exported distribution;
- secret-scan imported history and the final combined history;
- inspect untracked and ignored source worktrees without copying that data;
- import only Git-tracked content from disposable clones.

Validation must use `git check-ignore` or an equivalent repository-owned check
for every location where a setup wizard can create the backup.

No `.dbdata`, certificates, private keys, provider tokens, caches, virtual
environments, `node_modules`, build output, or generated runtime state may enter
the import.

## Git History Strategy

Use the same history-preserving approach proven for Studio:

1. Clone the source repository into a disposable location.
2. Run secret and large-file scans.
3. Rewrite tracked paths into the final destination directory with
   `git filter-repo --to-subdirectory-filter`.
4. Namespace imported tags in the disposable clone.
5. Validate tree identity and reachable commit counts.
6. Merge without squashing and with unrelated histories explicitly allowed.
7. Remove the temporary remote.
8. Record commands, source tips, rewritten tips, tree IDs, and validation in
   `MONOREPO_MIGRATION_RECORD.md`.

Tag treatment:

- preserve existing monorepo `sdk-python-v*` and `studio-v*` tags;
- import minimal deployment historical tags as `studio-minimal-v*`;
- import VM/Caddy historical tags as `studio-deployment-v*`;
- do not create new independent deployment tag streams after cutover;
- the website currently has no release-tag requirement; do not invent one.

Do not use continuing submodules or subtrees. The result is an ordinary
monorepo with one canonical source tree.

## One-Way Distribution Model

The minimal and VM/Caddy repositories remain publicly cloneable after cutover.
They are published projections of monorepo source.

Required behavior:

- the monorepo directory is the only editable source;
- each external README states that the repository is generated and links to the
  canonical directory;
- pull requests and issues that propose source changes are redirected to the
  monorepo;
- mirror publication exports only the owning deployment directory;
- the export includes Apache-2.0 `LICENSE` and excludes local state;
- publication occurs after the corresponding `studio-v*` images and deployment
  tests pass;
- publication is one way and never imports mirror commits back into the
  monorepo;
- the minimal repository remains a GitHub template;
- the VM/Caddy repository should also be evaluated as a GitHub template;
- each Studio release may attach self-contained deployment zip or tar archives
  in addition to updating mirrors.

Mirror automation must be explicit about credentials, destination branch,
expected source commit, and failure behavior. A failed mirror publication fails
the distribution portion of the release visibly; it must not silently leave a
repository claiming support for a version it does not contain.

## Version And Release Rules

### Python SDK

- Tag: `sdk-python-v<version>`
- Artifact: PyPI `junjo`
- Working directory: `sdks/python`
- Credentials: Python publishing environment only

### Studio

- Tag: `studio-v<version>`
- Artifacts: backend, frontend, and ingestion images
- Additional artifacts: minimal and VM/Caddy deployment snapshots
- Working directory: `apps/studio`
- Credentials: Studio image and deployment-distribution environments only

Both deployment Compose files remain self-contained and explicitly pin released
images. CI asserts that every pinned Studio image tag equals
`apps/studio/VERSION`. README compatibility statements must be validated against
the same release input.

Do not create a runtime dependency from a deployment directory to the rest of
the repository. Exported deployments must work after the directory is copied
out of the monorepo.

### Website

- Trigger: validated changes beneath `apps/website`
- Artifact: static site
- Environment: independent website hosting environment
- Version: no artificial shared platform version

Website publication is independent from SDK and Studio releases.

## CI Plan

### Deployment validation

Changes to `apps/studio/deployments/**`, Studio runtime configuration, or
`apps/studio/VERSION` run the affected deployment checks.

For both distributions:

- render `docker compose config` using safe fixture environment values;
- assert the three Studio image repositories and tags;
- assert required service names, internal ports, public ports, volumes, health
  checks, and environment variables;
- validate setup-wizard development and production paths;
- validate generated secret format without exposing values;
- validate URL and hostname behavior;
- test repeated setup and `.env.bak` handling;
- assert secret-bearing files are ignored and absent from archives;
- validate README version and compatibility statements;
- build a self-contained release archive and inspect its inventory.

Additional minimal checks:

- confirm the distribution includes only the three core Studio services;
- confirm it does not acquire an implicit reverse proxy or demo application;
- validate the reference Caddy example independently.

Additional VM/Caddy checks:

- validate Caddy configuration;
- build the Caddy image and Junjo demo application;
- validate the demo application's SDK pin and current API use;
- run an end-to-end smoke test that starts Studio, emits telemetry, and proves
  ingestion and queryability before distribution publication;
- verify production setup guidance does not expose internal RPC ports.

### Website validation

Changes to `apps/website/**` run a path-scoped website workflow:

- clean dependency installation from its own lock;
- Astro/type checking;
- lint or formatting checks once explicitly configured;
- production static build;
- internal link validation;
- checks for known obsolete Junjo repository names and URLs;
- deployment dry run against the selected host.

Do not create a root npm workspace or merge the website lock with the Studio
frontend lock.

### Licensing validation

Add a repository-owned check that verifies:

- expected Apache-2.0 component licenses exist;
- Junjo-owned AGPL declarations are absent;
- deployment archives include Apache-2.0;
- required third-party notices remain present.

### Existing validation

Continue to route existing Python, Studio, telemetry-contract, and release
checks by their owning paths. A deployment or website migration is not a reason
to weaken existing component validation.

## Repository Surfaces To Update During Implementation

The migration is not complete while high-authority repository guidance still
describes the previous layout or license. Update these surfaces in the same
commits that make their statements true:

- root `README.md`: add website and deployment ownership and replace the mixed
  Apache/AGPL explanation;
- root `AGENTS.md`: route website and deployment work to their owners and
  validation gates;
- `apps/studio/AGENTS.md`: add supported deployment distributions to the Studio
  domain map;
- `apps/studio/README.md`: replace AGPL text and describe external deployment
  repositories as generated distributions;
- `contracts/telemetry/README.md`: remove obsolete separate-license language;
- `sdks/python/RELEASE_POLICY.md`: replace manual template-update instructions
  with validated one-way publication;
- `tooling/scripts/validate_repository.py`: require the expanded layout,
  Apache-2.0 state, release routing, and distribution invariants;
- Studio and deployment `.gitignore` files: correctly ignore `.env.bak`;
- external deployment READMEs: identify the canonical monorepo source and
  generated status;
- website README and hosting configuration: identify `apps/website` as source.

Current-state documentation was updated only with repository changes that have
passed the repository validation gate. External hosting, mirror, environment,
and archival claims remain pending until their operator evidence is recorded.

## Migration Phases

### Phase 0: Align decisions and inventory

Work:

- update ADR 0001 and this migration plan;
- mark the initial migration record as partial rather than platform-complete;
- record source repository visibility, branches, tags, releases, issues,
  secrets, hosting, and environments;
- identify every current license declaration;
- inventory website hosting and domain ownership;
- inventory external deployment repository settings;
- refresh source revisions immediately before implementation.

Exit criteria:

- accepted docs describe one unambiguous target;
- no open directory, license, source-of-truth, or distribution-direction
  decision remains;
- source work is safely preserved;
- implementation inputs are recorded.

### Phase 1: Protect source work and prepare clean imports

Work:

- commit and back up the current website redesign without rewriting it;
- commit `.env.bak` ignore protection in current Studio and both deployment
  source repositories;
- refresh and record all source tips after those protection commits;
- create disposable clean clones from recorded source revisions;
- scan each source history for secrets and large files;
- inspect ignored and untracked files separately;
- add or plan fingerprint-scoped false-positive handling without broad secret
  exclusions;
- rehearse all three imports end to end.

Exit criteria:

- no source work exists only in an uncommitted checkout;
- every selected source tip includes the applicable `.env.bak` protection;
- scans pass or have narrow reviewed findings;
- rewritten trees match source trees at the selected tips;
- tags and paths do not collide;
- exact import commands are ready.

### Phase 2: Import minimal deployment

Work:

- verify the rehearsed source includes `.env.bak` protection;
- import history beneath `apps/studio/deployments/minimal`;
- preserve the distribution's root-level `docker-compose.yml` clone-and-run
  interface;
- remove source-repository-only synchronization machinery;
- update links to canonical Studio and SDK locations;
- add Compose, setup, version, archive, and secret-file validation.

Exit criteria:

- useful history and namespaced historical tags are reachable;
- the distribution renders and passes contract checks;
- archives are self-contained and contain no secret-bearing files;
- no manual upstream-diff instructions remain necessary.

### Phase 3: Import VM/Caddy deployment

Work:

- verify the rehearsed source includes `.env.bak` protection;
- import history beneath `apps/studio/deployments/vm-caddy`;
- preserve the operator walkthrough, Caddy surface, and demo application;
- remove source-repository-only synchronization machinery;
- update demo application and compatibility links;
- add Caddy, image, demo, telemetry, archive, and secret-file validation.

Exit criteria:

- useful history and namespaced historical tags are reachable;
- Caddy and Compose validate;
- the example application builds and emits observable telemetry;
- the deployment is self-contained outside the monorepo;
- no secret-bearing backup is tracked or exported.

### Phase 4: Import website

Work:

- confirm private-history publication and asset licensing;
- import the preserved website history beneath `apps/website`;
- keep its npm project and lock independent;
- replace starter and obsolete product content;
- configure the canonical site URL and hosting path;
- add website CI and deployment dry run;
- update platform navigation without duplicating Python API docs.

Exit criteria:

- website history and current redesign work are present;
- clean install and production build pass;
- links and terminology match current Junjo components;
- hosting configuration is ready for cutover;
- the website does not depend on Studio frontend internals.

### Phase 5: Establish Apache-2.0 licensing

Work:

- replace Studio AGPL-3.0 license and owned notices;
- add Apache-2.0 licenses to website and deployment export roots;
- update owned package, README, container, and website metadata;
- add licensing validation.

Exit criteria:

- every Junjo-owned component and export is Apache-2.0;
- no owned AGPL declaration remains;
- third-party notices remain intact;
- root documentation reflects the implemented state.

### Phase 6: Build Studio distribution release flow

Work:

- extend `studio-v*` validation to both deployments;
- build deployment archives;
- implement one-way mirror publication;
- add generated-source notices;
- define narrowly scoped mirror credential and environment requirements;
- test publication to disposable or non-production destinations;
- verify mirror output exactly matches the exported source tree.

Exit criteria:

- a Studio release cannot publish mismatched image and deployment versions;
- external distributions are reproducible from a recorded monorepo commit;
- direct mirror edits are not part of the workflow;
- failure is visible and recoverable without changing canonical source.

### Phase 7: Repository completion gate and Agent work resumption

Work:

- run all component and cross-contract validation;
- run combined-history secret scanning;
- validate release routing and credential isolation without production
  publication;
- validate website deployment and both mirror publications against disposable or
  non-production destinations;
- inspect release archives and mirror inventories;
- append import and validation evidence to the migration record;
- update root maps, scoped instructions, and Agent roadmap references to the
  implemented layout.

Exit criteria:

- ADR, plan, record, root documentation, and implementation agree;
- all histories and tags are discoverable and unambiguous;
- all current Junjo-owned source and artifacts are Apache-2.0;
- SDK, Studio, deployments, website, and contracts pass their independent
  checks;
- release archives and one-way distribution output are reproducible;
- production publishing remains disabled until external cutover is authorized.

Agent implementation may resume after this repository-complete gate. It is not
blocked on hosting credentials, repository archival, or other external operator
state.

### Phase 8: External cutover and post-cutover verification

Work:

- configure destination branch protection and informational CI checks;
- configure website hosting secrets and environment;
- configure deployment mirror credentials;
- publish and verify the website from `apps/website`;
- publish and verify both generated deployment repositories;
- publish Apache-2.0 license and current-source notices to surviving or archived
  repository default branches;
- archive the old website source repository with a redirect;
- retain deployment repositories as generated distributions;
- update GitHub descriptions, template status, links, issues, and contribution
  guidance;
- complete any remaining original Studio source-repository archival work;
- append external cutover results to the migration record.

Exit criteria:

- public links resolve to current source or distribution locations;
- website production deployment is sourced only from the monorepo;
- deployment repositories match monorepo export content;
- current default branches and published artifacts use Apache-2.0;
- archived source repositories cannot publish competing artifacts;
- operators retain a simple clone experience;
- external cutover does not invalidate the Phase 7 repository validation.

## Validation Checklist

### Repository integrity

- exact source and rewritten revisions recorded
- source and imported tree identities checked
- useful histories reachable
- imported tags namespaced
- ignored runtime state absent
- combined-history secret scan passes
- repository validation script knows all new owned paths

### Licensing

- root Apache-2.0 license valid
- Python component Apache-2.0 license valid
- Studio Apache-2.0 license valid
- website Apache-2.0 license valid
- both deployment exports include Apache-2.0
- owned AGPL text absent
- third-party notices retained

### Python SDK and telemetry

- Ruff
- pytest
- ty
- Sphinx without new warnings
- package build and Twine validation
- installed-wheel smoke test
- telemetry contract conformance

### Studio

- backend tests and Ruff
- frontend tests, lint, and production build
- ingestion locked tests
- protobuf staleness
- REST contract validation
- development and production Compose rendering
- production image builds
- Studio version synchronization

### Deployment distributions

- Compose rendering
- image tag synchronization
- environment and port contract checks
- setup-wizard tests
- `.env` and `.env.bak` exclusion
- release archive inventory
- Caddy validation where applicable
- demo application build and telemetry smoke test where applicable
- one-way mirror dry run

### Website

- clean dependency install
- static/type checks
- production build
- link validation
- obsolete terminology check
- deployment dry run

### Release isolation

- Python tags cannot trigger Studio or website publication
- Studio tags cannot trigger PyPI or website publication
- website changes cannot obtain PyPI or Studio credentials
- mirror jobs receive only mirror credentials
- deployment mirrors publish only after Studio artifacts validate

## Risks And Mitigations

### Dirty website work is lost

Mitigation: preserve and push the current work before creating disposable
history-rewrite clones. Never run filtering commands in the working checkout.

### Distribution mirrors become competing sources

Mitigation: one-way publication, generated notices, source links, and no
bidirectional synchronization.

### Studio releases and deployment pins drift

Mitigation: validate exact image tags and compatibility statements during every
`studio-v*` release before publication.

### Secrets enter history or archives

Mitigation: explicitly ignore `.env.bak`, scan histories, inspect archive
inventories, and publish only from clean tracked exports.

### Relicensing is only partially applied

Mitigation: update license files, owned notices, manifests, docs, archives, and
container metadata together; add an automated absence check for owned AGPL
declarations.

### Monorepo creates dependency coupling

Mitigation: retain independent locks and working directories. Use contracts and
CI orchestration rather than runtime imports.

### Website documentation duplicates SDK documentation

Mitigation: keep Python API ownership in Sphinx and website ownership at the
platform/product layer.

### External cutover breaks operator workflows

Mitigation: retain small deployment repositories, preserve clone commands,
test generated artifacts, and archive only repositories that no longer serve a
distribution purpose.

## Branch And Change Hygiene

Continue the expanded migration on the dedicated branch:

```text
codex/platform-monorepo-migration
```

Before implementation:

- confirm the branch contains the validated initial SDK/Studio migration;
- commit these planning changes separately from source imports;
- refresh all source revisions;
- ensure the destination and import clones are clean;
- preserve unrelated local work;
- avoid Agent runtime changes during structural migration.

Each import, relicensing change, validation layer, and external publication
workflow should be reviewable as a coherent commit. Do not combine unrelated
runtime refactors with the migration.

## Definition Of Done

The repository migration is complete when:

- SDK, Studio, website, and supported deployment source live in the monorepo;
- useful histories and tags are preserved and recorded;
- all Junjo-owned source and distributions are Apache-2.0;
- `.env.bak` and other secret-bearing local state are ignored and excluded;
- each independently deployable product retains its own dependencies, build,
  and release boundary;
- deployment distributions remain self-contained artifacts released with
  Studio;
- Studio release dry runs validate and export both deployment distributions;
- external deployment repository output is reproducible as a one-way mirror;
- the website builds and passes a deployment dry run from `apps/website`;
- root and scoped documentation match the implemented layout;
- all component, contract, release, and security validation passes;
- Agent work can proceed without coordinating changes across competing source
  repositories.

External cutover is complete when the website and distribution mirrors are
published from the monorepo, current external default branches use Apache-2.0,
and obsolete source repositories are archived or converted to generated
distributions as appropriate.

Copying files is not repository completion. Source ownership, history,
licensing, builds, tests, release dry runs, distribution generation, and
documentation must agree before Agent implementation resumes. Production
hosting and external repository cutover are then verified as an operator phase.
