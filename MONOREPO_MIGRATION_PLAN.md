# Junjo Monorepo Migration Plan

## Status

Proposed planning document. No repository consolidation has been approved or
performed.

This plan describes how to consolidate the current `junjo` Python SDK and
`junjo-ai-studio` repositories into one Junjo platform monorepo without
combining their runtime responsibilities, dependency graphs, versions, or
deployment artifacts.

The consolidation should be completed before substantial Agent-layer runtime
implementation begins so Agent execution and Studio diagnostics can evolve as
one atomic cross-system contract.

## Recommendation

Use the existing `junjo` repository as the destination monorepo.

The destination should contain:

- independently versioned language SDKs
- independently deployed Junjo AI Studio services
- shared telemetry contracts and conformance fixtures
- cross-platform ADRs and roadmaps
- examples that validate SDK and Studio integration

Monorepo means one source tree and one integration boundary. It does not mean:

- one package
- one version
- one dependency lock
- one deployment artifact
- one runtime process
- direct SDK dependencies on Studio
- direct Studio dependencies on a particular SDK implementation

## Why Consolidate Before Agent Implementation

The Agent layer crosses the current repository boundary by design:

```text
Junjo SDK
  -> Agent execution and state
  -> model and Tool telemetry
  -> Agent/Workflow nesting

Junjo AI Studio
  -> ingestion contract preservation
  -> Agent execution queries
  -> state reconstruction
  -> dynamic Agent timeline
  -> nested Workflow Graph visualization
```

Implementing this in separate repositories would require coordinated commits,
fixtures, CI runs, tags, and releases for every telemetry-contract change.

A monorepo allows one pull request to contain:

- SDK emission changes
- canonical contract fixtures
- Studio ingestion assertions
- backend query changes
- frontend schema and diagnostic changes
- AI Chat acceptance behavior
- cross-system documentation

The code remains separated by responsibility even though compatibility changes
are reviewed atomically.

## Current Release Boundaries To Preserve

### Junjo Python SDK

Current artifact:

- PyPI project: `junjo`
- Python import: `junjo`
- supported Python: 3.11+
- build: setuptools through `python -m build`
- release: GitHub Release triggers PyPI trusted publishing

The monorepo migration must not change the installed package name, import path,
public API, or wheel contents except for intentional future SDK changes.

### Junjo AI Studio

Current artifacts:

- backend Docker image
- frontend Docker image
- ingestion Docker image

Studio currently versions and releases those three services together. Preserve
that service-level version synchronization after the move.

### Shared Compatibility

The Python SDK and Studio currently use separately numbered paired releases.
The monorepo should preserve independent product versions while adding an
explicit telemetry-contract version and compatibility tests.

## Target Repository Structure

```text
junjo/
├── AGENTS.md
├── README.md
├── LICENSE
├── Taskfile.yml                         # Optional root orchestration
│
├── sdks/
│   ├── python/
│   │   ├── AGENTS.md
│   │   ├── pyproject.toml
│   │   ├── uv.lock
│   │   ├── README.md
│   │   ├── src/junjo/
│   │   ├── tests/
│   │   ├── docs/                       # Python public Sphinx docs
│   │   └── examples/
│   │       ├── ai_chat/
│   │       ├── base/
│   │       └── getting_started/
│   │
│   ├── typescript/                     # Future
│   ├── rust/                           # Future
│   └── go/                             # Future
│
├── apps/
│   └── studio/
│       ├── AGENTS.md
│       ├── VERSION
│       ├── README.md
│       ├── compose.yaml
│       ├── backend/
│       ├── frontend/
│       ├── ingestion/
│       ├── proto/
│       ├── docs/adr/                   # Studio-owned decisions
│       ├── scripts/
│       └── test-fixtures/
│
├── contracts/
│   └── telemetry/
│       ├── README.md
│       ├── VERSION
│       ├── schemas/
│       ├── fixtures/
│       └── compatibility/
│
├── docs/
│   ├── adr/                            # Cross-platform decisions
│   └── roadmaps/
│
├── tooling/
│   └── scripts/
│
└── .github/
    └── workflows/
```

This is the preferred end-state shape. Exact file locations should be validated
during a rehearsal migration before final cutover.

## Directory Ownership

### Root

The repository root owns only platform-wide concerns:

- platform overview
- cross-system contribution entrypoints
- root task orchestration
- cross-platform ADRs
- shared telemetry contracts
- integration CI
- release routing

The root must not become a duplicate source of truth for SDK or Studio
implementation details.

### `sdks/python`

Owns:

- Python Junjo runtime
- Python public API and docstrings
- Python unit and contract tests
- Python Sphinx documentation
- Python package metadata
- Python SDK examples
- PyPI release workflow inputs

### `apps/studio`

Owns:

- Studio backend
- Studio frontend
- Studio ingestion
- Studio-internal protobuf contracts
- Studio deployment configuration
- Studio service version
- Studio implementation ADRs
- Studio Docker image releases

### `contracts/telemetry`

Owns language-independent compatibility artifacts:

- telemetry contract version
- canonical attribute and event definitions
- JSON schemas for serialized snapshots
- golden OTLP or normalized JSON fixtures
- expected hierarchy and state reconstruction outcomes
- SDK emitter conformance cases
- Studio consumer conformance cases

It must not contain runtime business logic from any SDK or Studio service.

### `docs/adr`

Owns decisions that cross more than one deployable or language implementation,
including:

- monorepo structure and release boundaries
- cross-language telemetry semantics
- SDK/Studio compatibility policy
- future shared experience-definition contracts

Python-only runtime ADRs should live under `sdks/python/docs/adr/`. Studio-only
ADRs should remain under `apps/studio/docs/adr/`. Ingestion-specific ADRs remain
under `apps/studio/ingestion/adr/`.

## Instruction File Strategy

The current repositories have materially different guidance. A monorepo
justifies scoped instruction files because the rules differ on every task within
those directories.

### Root `AGENTS.md`

Keep the root file short and platform-oriented:

- shared developer philosophy
- repository map
- cross-system contract rules
- ADR ownership
- change hygiene
- validation routing

### `sdks/python/AGENTS.md`

Move and adapt the current Junjo SDK guidance:

- public docstrings and Sphinx rules
- Graph/Workflow/State/Store boundaries
- telemetry and hook separation
- Python validation commands
- example teaching rules

### `apps/studio/AGENTS.md`

Move and adapt the current Studio guidance:

- backend, ingestion, and frontend ownership
- migration rules
- Studio validation commands
- source-of-truth rules
- subsystem skills

Existing nested Studio skills should move with Studio and remain the preferred
home for task-specific subsystem guidance.

## Dependency And Workspace Strategy

Do not create one repository-wide dependency graph.

### Python SDK Workspace

`sdks/python` should remain its own uv workspace containing the SDK and its
Python examples.

It preserves:

- Python 3.11+ support
- SDK development dependencies
- workspace installation of `junjo` into examples
- one SDK/example lock strategy

### Studio Backend

`apps/studio/backend` remains a separate Python 3.13 uv project with its own
lock file. Do not add it to the Python SDK workspace.

### Studio Frontend

`apps/studio/frontend` retains its own `package.json` and npm lock.

### Studio Ingestion

`apps/studio/ingestion` retains its own Cargo manifest and lock.

### Future SDKs

Each future SDK owns its idiomatic package manager and lock files:

- TypeScript: npm/pnpm package and lock
- Rust: Cargo package and lock
- Go: Go module files

Root tasks may orchestrate these projects but must not merge their dependency
resolution.

## Python Package Publishing From The Monorepo

The Python SDK can publish normally from `sdks/python`.

Conceptual release steps:

```text
checkout repository
  -> set up Python 3.11
  -> install uv
  -> run SDK checks from sdks/python
  -> build sdks/python/dist/*
  -> validate wheel and source distribution
  -> publish those artifacts to PyPI
```

Preserve:

- `[project].name = "junjo"`
- `src/junjo` package discovery
- Python version support
- project URLs
- license inclusion
- README rendering
- trusted publishing environment

Update only repository-relative paths and workflow working directories.

Before cutover, build distributions from the old and migrated layouts at the
same source commit and compare:

- wheel file list
- source distribution file list
- package metadata
- import behavior
- installed public API
- tests against the built wheel

The archive bytes need not be identical because paths and timestamps can vary.
The installed behavior and intended contents must be equivalent.

## Independent Version And Tag Strategy

Monorepo products remain independently versioned.

Use namespaced tags going forward:

```text
sdk-python-v0.64.0
studio-v0.82.0
sdk-typescript-v0.1.0
sdk-rust-v0.1.0
```

### Python SDK Release

Triggered only by `sdk-python-v*` tags or a corresponding GitHub Release.

Publishes:

- PyPI `junjo`
- Python SDK release notes
- optionally built Sphinx documentation

### Studio Release

Triggered only by `studio-v*` tags or a corresponding GitHub Release.

Publishes synchronized versions of:

- Studio backend image
- Studio frontend image
- Studio ingestion image

### Future SDK Releases

Each language uses its own tag prefix and package registry.

### Existing Tags

Do not rewrite or delete existing Junjo tags.

When importing Studio history, namespace imported Studio tags or leave them in
the archived Studio repository. Do not create ambiguous unprefixed tags in the
destination.

The rehearsal migration must determine which tag-import approach preserves the
most useful history without colliding with existing tags.

## Telemetry Contract Versioning

Add a telemetry-contract version independent of SDK and Studio versions.

Conceptual compatibility:

```text
Python SDK 0.64.0
  emits telemetry contract 3

TypeScript SDK 0.8.0
  emits telemetry contract 3

Studio 0.82.0
  consumes telemetry contract 3
```

During greenfield development, Studio may support only the active telemetry
contract. The version still must be explicit so failures are diagnosable and
future language SDKs can prove conformance.

The contract version should be present in canonical fixtures and emitted
telemetry according to a cross-platform ADR.

## Future Language SDK Strategy

Additional SDKs should share concepts and observable contracts, not a mechanical
translation of Python implementation details.

Every SDK should preserve these platform semantics where supported:

- reusable definitions and isolated runs
- explicit Graph or Agent execution identity
- state transition ordering
- failure and cancellation semantics
- Graph snapshot schema
- Agent definition snapshot schema
- Tool and model-operation semantics
- telemetry contract version

Language implementations remain idiomatic:

- Python may use Pydantic and asyncio
- TypeScript may use Zod and promises
- Rust may use Serde and Tokio
- Go may use structs and contexts

The conformance suite should state expected outcomes without requiring identical
internal class hierarchies.

## Git History Preservation

The migration should preserve both repositories' useful history.

### Destination

Use the current `junjo` repository and its history as the destination.

### Python SDK Move

Move current Junjo SDK files into `sdks/python` using normal Git moves in a
dedicated migration commit. Git history remains reachable, and `git log
--follow` can trace renamed files.

Platform-level files created during the Agent strategy work move to root
`docs/roadmaps` or root `docs/adr` as appropriate rather than into the Python
package.

### Studio Import

Import Studio through a rehearsed history-preserving method that rewrites or
places its paths beneath `apps/studio` before combining histories.

Candidate methods:

1. Prepare a temporary Studio clone with `git filter-repo
   --to-subdirectory-filter apps/studio`, then merge the rewritten branch into
   Junjo.
2. Use a one-time, non-squashed Git subtree import beneath `apps/studio`.

Prefer the method that:

- avoids root path collisions
- preserves commit authorship and messages
- keeps file history discoverable
- does not require rewriting existing Junjo public history
- produces an ordinary repository after migration, without a continuing
  subtree/submodule workflow

Do not use a Git submodule. The objective is atomic changes and shared CI, which
a submodule would not provide.

### Rehearsal

Perform the entire import in disposable local clones first. Record exact
commands and validate the resulting history before touching the destination
remote.

### Issues, Releases, And Pull Requests

Git history does not migrate GitHub issues, releases, discussions, or pull
request metadata automatically.

Before archiving Studio:

- export or inventory open issues
- recreate active roadmap items in Junjo
- preserve links to historical Studio releases
- update repository URLs in package metadata and documentation
- add an archive notice and destination link to Studio

## CI Architecture

Use path-filtered workflows and a small number of integration gates.

### Python SDK CI

Triggered by changes to:

- `sdks/python/**`
- shared telemetry contracts consumed by Python
- Python SDK workflow definitions

Runs:

- Ruff
- pytest
- ty
- Sphinx
- package build and validation
- Python telemetry conformance fixtures
- Python examples smoke tests

### Studio CI

Triggered by changes to:

- `apps/studio/**`
- shared telemetry contracts consumed by Studio

Runs the existing scoped checks:

- backend tests and Ruff
- frontend tests, lint, and build
- ingestion Rust tests
- protobuf staleness
- REST API contract validation
- Studio service version synchronization

### Cross-Contract CI

Triggered by changes to:

- `contracts/telemetry/**`
- any SDK telemetry emitter
- Studio ingestion/backend/frontend telemetry consumers

Runs:

- SDK generation or loading of canonical fixtures
- Studio ingestion preservation tests
- Studio backend semantic query tests
- Studio frontend schema and reconstruction tests
- nested Workflow/Agent diagnostic fixtures

### Root Integration CI

Runs only the minimal end-to-end checks that prove repository integration.
Avoid running every language and service build for unrelated documentation or
component-local changes.

### Required Checks

Branch protection should require checks based on changed paths where GitHub
configuration permits. Ensure skipped path-filtered workflows do not leave
required checks permanently pending.

## Release Workflow Migration

### Python

Update the existing publish workflow to:

- recognize only Python SDK release tags
- run with `sdks/python` as the project directory
- upload only `sdks/python/dist/*`
- verify the release commit is reachable from the default branch
- keep PyPI trusted publishing narrowly scoped

### Studio

Update the Docker matrix workflow to:

- recognize only Studio release tags
- read `apps/studio/VERSION`
- use `apps/studio` build context
- continue building amd64 and arm64 images
- retain current image repository names unless a separate branding decision is
  made

### Secrets And Environments

Inventory and recreate repository secrets and deployment environments in the
destination before disabling Studio workflows.

Keep release permissions scoped per job:

- PyPI environment for Python publishing
- Docker credentials for Studio publishing
- future registry credentials for other SDKs

Monorepo access must not grant every workflow every publishing credential.

## Documentation Migration

### Platform Documentation

Root README should explain:

- what Junjo is
- available SDKs
- Junjo AI Studio
- repository navigation
- component release and installation links

### Python Public Documentation

Move existing Sphinx documentation with the Python SDK unless a page is truly
platform-wide.

Preserve:

- Python API documentation URLs
- public docstrings
- examples and tutorials
- PyPI links
- Studio setup references

### Studio Documentation

Move Studio onboarding and operations docs beneath `apps/studio` and update all
relative links.

### Roadmaps And ADRs

Move current Agent roadmap documents to root `docs/roadmaps` because Agent
telemetry and Studio diagnostics are cross-platform work.

Create a root monorepo ADR before migration. Existing proposed Agent ADR paths
and numbers are provisional and should be assigned within the final monorepo
ownership structure after the monorepo ADR is accepted.

## Proposed Monorepo ADR

Create before implementation:

### `docs/adr/0001-junjo-platform-monorepo.md`

Owns:

- decision to use one repository
- target directory structure
- component ownership
- independent version and release policy
- dependency and lock-file separation
- shared telemetry-contract ownership
- future language SDK placement
- root versus component ADR ownership
- history-preservation strategy
- archived Studio repository policy

The ADR should not duplicate step-by-step migration commands. Commands and
validation results belong in this plan or a migration runbook.

## Migration Phases

### Phase 0: Inventory And ADR Approval

#### Work

- accept the monorepo ADR
- inventory repository branches, tags, releases, issues, secrets, environments,
  packages, images, and external links
- inventory ignored local data that must never be imported
- record current validation commands and successful baselines
- choose default branch naming
- choose history-import method through rehearsal
- finalize directory ownership

#### Exit criteria

- ADR accepted
- inventory complete
- both repositories pass their current validation gates
- exact rehearsal commands documented
- no unresolved tag or path collision

### Phase 1: Create The Platform Skeleton

#### Work

- create root platform README and AGENTS guidance
- create `sdks`, `apps`, `contracts`, and root docs structure
- move Python SDK using Git moves
- restore Python uv workspace with examples
- update Python-local paths without changing runtime behavior

#### Exit criteria

- Python SDK tests pass from its new directory
- Sphinx builds
- examples resolve the workspace SDK
- wheel and source distribution validate
- installed public API matches the pre-migration build

### Phase 2: Import Studio History

#### Work

- import rehearsed Studio history beneath `apps/studio`
- resolve root metadata collisions intentionally
- preserve Studio VERSION and service layout
- move Studio instruction and skill files
- update internal relative paths

#### Exit criteria

- Studio file history is discoverable
- no Junjo SDK files were overwritten
- no local databases, build products, secrets, or caches were imported
- Studio commands run from the documented directory

### Phase 3: Restore Studio Builds And Tests

#### Work

- update Docker build contexts and Compose paths
- update backend scripts and locks
- update frontend scripts and locks
- update Rust/protobuf paths
- update version synchronization scripts
- run the full Studio validation suite

#### Exit criteria

- backend tests and lint pass
- frontend tests, lint, and build pass
- ingestion tests pass
- protobuf staleness check passes
- REST API contracts pass
- development and production Compose render successfully
- all three production images build locally or in CI

### Phase 4: Establish Shared Telemetry Contracts

#### Work

- create telemetry contract README and version
- move or copy canonical fixtures into contract ownership
- define fixture generation ownership
- add Python emitter conformance checks
- add Studio consumer conformance checks
- ensure existing Workflow state and Graph fixtures pass before Agent changes

#### Exit criteria

- current Python SDK telemetry is represented by canonical fixtures
- Studio ingests and renders the fixtures correctly
- one command or CI workflow validates the full contract
- SDK and Studio package versions are not used as a substitute for contract
  identity

### Phase 5: Rebuild CI Boundaries

#### Work

- move workflows into the destination `.github/workflows`
- add path filtering
- preserve component-specific caches
- add cross-contract CI
- add repository integration smoke checks
- configure required-check behavior

#### Exit criteria

- Python-only changes run Python and relevant contract checks
- Studio-only changes run Studio and relevant contract checks
- contract changes run all producers and consumers
- unrelated paths do not run every expensive job
- all release workflows remain disabled or dry-run-only until cutover approval

### Phase 6: Rebuild Independent Releases

#### Work

- implement namespaced tag routing
- update PyPI build paths and trusted publisher configuration
- update Studio Docker build paths
- inventory and restore secrets/environments
- test artifact creation without publishing
- validate version/tag mismatch failures

#### Exit criteria

- Python dry run builds the expected wheel and source distribution
- Studio dry run builds all expected images
- a Python tag cannot trigger Studio publishing
- a Studio tag cannot trigger PyPI publishing
- release jobs have only their required credentials

### Phase 7: Documentation And External Cutover

#### Work

- update GitHub links, badges, package URLs, and clone instructions
- update Python documentation build/deployment configuration
- update Studio minimal-build and deployment-example references where necessary
- migrate active issues and roadmap items
- publish archive notice in `junjo-ai-studio`
- disable old Studio CI and releases

#### Exit criteria

- public Python installation instructions are unchanged for users
- Studio deployment instructions point to valid paths/images
- external repositories reference the monorepo source
- the old Studio repository is clearly archived and read-only
- no active publishing workflow remains in the archived repository

### Phase 8: Resume Agent Phase 0 And Horizon 1

#### Work

- move Agent roadmap and Phase 0 docs to root platform roadmap ownership
- write Agent ADRs in their final scopes
- write paired Agent telemetry and Studio diagnostics ADRs
- begin deterministic Agent kernel implementation only after those decisions are
  accepted

#### Exit criteria

- Agent work occurs entirely in the monorepo
- one branch can change SDK emission, fixtures, and Studio consumption
- the pre-Agent Workflow telemetry contract remains green

## Validation Checklist

### Repository Integrity

- both Git histories are reachable
- authorship and commit messages are preserved
- tags are unambiguous
- ignored build output and local data are absent
- Git LFS or large-file history is understood before import
- secret scanning passes across combined history

### Python SDK

- `uv run ruff check .`
- `uv run pytest -q`
- `uv run ty check --error-on-warning src`
- Sphinx HTML build without new warnings
- wheel and source distribution build
- `twine check`
- install wheel into a clean environment
- import and run a minimal Workflow
- examples use the workspace SDK

Commands will require their final `sdks/python` working directory after the
move.

### Studio

- backend test script
- backend Ruff
- frontend tests
- frontend lint
- frontend production build
- ingestion Cargo tests
- protobuf generation/staleness
- REST API contract validation
- Studio version synchronization
- development Compose render
- production Compose render
- three Docker production builds

### Cross-System

- Python emits canonical Workflow telemetry fixture
- ingestion preserves attributes and events
- backend returns expected traces
- frontend parses Graph and state events
- state patches reconstruct expected final state
- nested Subflow and concurrent execution fixtures still render
- paired contract CI passes from a clean checkout

### Release Dry Runs

- Python tag routing
- Studio tag routing
- artifact names and versions
- PyPI metadata
- Docker image tags
- amd64 and arm64 build configuration
- release credentials remain scoped

## Migration Risks And Mitigations

### Risk: Migration And Feature Work Become Entangled

Mitigation:

- isolate migration on its own branch
- freeze Agent runtime implementation during structural moves
- make behavior-preserving commits
- resume Agent work only after migration validation

### Risk: One Repository Creates Runtime Coupling

Mitigation:

- enforce directory ownership
- prohibit SDK imports from Studio
- prohibit Studio imports from SDK implementations
- communicate only through explicit telemetry/contracts
- retain separate dependency graphs and release artifacts

### Risk: CI Becomes Slow And Noisy

Mitigation:

- path-filter component workflows
- reserve full integration runs for contract changes
- preserve language-specific caches
- avoid a single mandatory root build command for every change

### Risk: Release Tags Trigger The Wrong Publisher

Mitigation:

- namespaced tags
- explicit tag validation in every publish workflow
- independent GitHub environments
- dry-run artifact builds before enabling publishing

### Risk: History Import Leaks Secrets Or Large Local Data

Mitigation:

- run secret and large-file scans on Studio history before import
- inspect ignored and untracked data separately
- rehearse in disposable clones
- never import working-directory caches or `.dbdata`

### Risk: Public Python Package Changes Accidentally

Mitigation:

- compare built artifacts
- install and test the wheel
- preserve package name/import metadata
- keep migration changes separate from public API changes

### Risk: Studio Archive Breaks External Links

Mitigation:

- leave the old repository visible and archived
- add prominent redirect documentation
- preserve historical releases
- update active external repositories before archival

## Cutover And Rollback

### Cutover

Do not enable new publishing workflows until all validation and dry-run gates
pass.

Recommended cutover order:

1. Merge the fully validated monorepo migration.
2. Confirm default-branch CI.
3. Enable namespaced Python release workflow.
4. Enable namespaced Studio release workflow.
5. Perform non-production or patch release smoke tests as appropriate.
6. Update external source links.
7. Archive Studio only after destination releases are proven.

### Rollback

Because the migration is additive to the Junjo repository, rollback before
cutover is a normal branch or merge revert.

Keep the Studio repository operational until:

- Studio builds pass in the destination
- Studio release dry runs pass
- secrets and environments are present
- the first destination Studio release path is proven

Do not delete the Studio repository. Archive it after successful cutover so its
history, issues, and releases remain accessible.

## Worktree And Branch Hygiene

Perform migration work on a dedicated branch separate from the Agent roadmap
branch.

Suggested branch:

```text
codex/platform-monorepo-migration
```

Before creating that branch:

- commit or otherwise intentionally preserve the current roadmap documents
- start from the agreed destination base commit
- ensure both repository worktrees are clean
- record both source commit SHAs in the migration notes

Do not mix unrelated runtime refactors into the migration commits.

## Definition Of Done

The monorepo migration is complete when:

- Junjo Python SDK and Studio source live in the destination repository
- both histories remain accessible
- Python publishes independently to PyPI
- Studio publishes its three images independently from Python
- each component retains its own dependency and version boundaries
- current Workflow telemetry passes a shared conformance suite
- root and nested documentation have clear ownership
- old Studio source repository is safely archived
- future SDK directories and release conventions are established
- Agent Phase 0 ADRs can be written against one repository and one shared
  telemetry contract

The migration must not be considered complete merely because files were copied
into one tree. It is complete only when builds, tests, releases, documentation,
history, and cross-system contracts all work from the new repository.
