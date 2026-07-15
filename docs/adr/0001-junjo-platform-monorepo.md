# ADR 0001: Junjo platform monorepo

- Status: Accepted
- Date: 2026-07-12
- Updated: 2026-07-13
- Owners: Junjo platform

## Context

Junjo is one platform with several independently built and deployed surfaces:

- language SDKs that execute Workflows and Agents;
- Junjo AI Studio, which ingests, queries, evaluates, and visualizes execution
  evidence;
- the Junjo website and platform documentation;
- supported Studio deployment distributions.

The Python SDK and Studio were initially developed in separate repositories.
The website, minimal Studio distribution, and VM/Caddy deployment example also
evolved in separate repositories. That separation makes coordinated changes to
telemetry contracts, product terminology, supported versions, deployment
configuration, documentation, and release validation depend on manual
synchronization.

The components still have different users, dependency graphs, runtime
responsibilities, build systems, release cadences, and deployment artifacts.
One repository must improve coordination without obscuring those boundaries.

## Decision

The existing `junjo` repository is the canonical source repository for the
Junjo platform.

The target layout is:

```text
junjo/
├── sdks/
│   └── python/
├── apps/
│   ├── studio/
│   │   └── deployments/
│   │       ├── minimal/
│   │       └── vm-caddy/
│   └── website/
├── contracts/
│   └── telemetry/
├── docs/
│   ├── adr/
│   └── roadmaps/
├── tooling/
└── .github/workflows/
```

Ownership is explicit:

- `sdks/python` owns the Python SDK, public API, examples, tests, package
  metadata, owned Python documentation, and its generated API contract.
- `apps/studio` owns Studio backend, frontend, ingestion, internal protobufs,
  service documentation, supported deployment distributions, and Studio
  releases.
- `apps/website` owns the Junjo marketing site, platform narrative, platform
  guides, and website deployment.
- `contracts/telemetry` owns language-independent telemetry schemas, versions,
  fixtures, and conformance expectations.
- root `docs` owns cross-platform decisions and roadmaps.
- root workflows route validation and publishing by component path and release
  identity.

Each independently deployable product keeps its own dependency lock, build,
version where one is useful, release artifact, and runtime. Deployment
distributions are self-contained artifacts released with Studio, not
independently versioned products. Contracts and documentation are not runtimes.
The monorepo is a source and review boundary, not one application runtime or one
dependency graph.

## Runtime and documentation boundaries

- SDKs may emit the shared telemetry contract but may not import Studio code.
- Studio consumes OpenTelemetry and shared fixtures but may not import an SDK
  implementation.
- Studio-internal gRPC protobufs remain in `apps/studio/proto`; they are not the
  public cross-language telemetry contract.
- shared contract directories contain schemas and conformance data, not SDK or
  Studio business logic.
- future SDKs own language-native dependencies and implementations while
  conforming to shared observable semantics.
- the website does not become a runtime dependency of an SDK or Studio.
- Python API documentation remains canonical under `sdks/python/docs`.
- the website owns platform and product documentation and may link to or
  publish generated SDK reference output; it must not create a second manually
  maintained Python API source of truth.

## Canonical source and distribution repositories

The two supported Studio deployment repositories have a different source
boundary and distribution boundary:

- canonical minimal deployment source lives in
  `apps/studio/deployments/minimal`;
- canonical VM/Caddy deployment source lives in
  `apps/studio/deployments/vm-caddy`;
- the existing standalone GitHub repositories remain small operator-facing
  distributions;
- standalone distributions are published one way from validated monorepo
  source;
- standalone distributions are not edited as co-equal sources of truth;
- each distribution contains a generated-source notice and a link to its
  canonical monorepo directory;
- changes are proposed against the monorepo and exported only after validation.

Keeping a cloneable distribution does not justify maintaining the deployment
contract independently from the Studio release that it deploys.

The website does not require a distribution mirror. After its deployment and
repository settings are cut over, its old source repository is archived with a
link to `apps/website`.

## Versions and releases

Product versions remain independent:

- `sdk-python-v<version>` routes only to the Python package release;
- `studio-v<version>` routes only to the Studio image and deployment release;
- future SDKs use `sdk-<language>-v<version>`;
- the telemetry contract uses its own integer version in
  `contracts/telemetry/VERSION`;
- the website deploys independently from its own validated path and does not
  receive an artificial platform version.

The minimal and VM/Caddy deployments do not have independent future product
versions. A `studio-v<version>` release owns:

1. the synchronized backend, frontend, and ingestion images;
2. the supported deployment snapshots pinned to those images;
3. validation that deployment configuration matches the released Studio
   runtime contract;
4. release archives and one-way publication of the standalone distributions.

Distribution publication occurs only after the Studio images and deployment
checks succeed.

Product versions are not implicit telemetry contract identifiers. Every Junjo
executable span carries the explicit telemetry contract version required by the
active contract.

## Telemetry contract ownership

`contracts/telemetry` is the canonical owner of current interoperability
fixtures and schemas. A semantic change requires one atomic change containing:

1. an explicit contract-version decision;
2. updated schemas and canonical fixtures;
3. affected SDK emitter assertions;
4. affected Studio ingestion, backend, and frontend assertions;
5. documentation of the compatibility change.

## Git history

Useful source histories are preserved during component import.

- The original Junjo history remains the destination history.
- Studio history was imported beneath `apps/studio` without squashing.
- Website history is imported beneath `apps/website` after all current local
  work is committed and publication of its private history is approved.
- Minimal deployment history is imported beneath
  `apps/studio/deployments/minimal`.
- VM/Caddy deployment history is imported beneath
  `apps/studio/deployments/vm-caddy`.
- Imported historical tags are namespaced so they cannot collide:
  `studio-v*`, `studio-minimal-v*`, and `studio-deployment-v*`.
- Deployment imports do not create continuing subtree, submodule, or
  bidirectional synchronization workflows.

Exact source revisions, commands, scans, and validation results belong in the
monorepo migration record rather than this ADR.

## Licensing

All Junjo-authored source, applications, documentation, contracts, examples,
and deployment distributions are licensed under Apache License 2.0. ADR 0002
defines the required boundary between Junjo-authored work and third-party
material and governs historical Catalyst provenance.

Implementation of this decision includes:

- applying the Apache-2.0 license and notices to Studio;
- keeping or adding an Apache-2.0 `LICENSE` in every independently packaged or
  exported component;
- including Apache-2.0 in both standalone deployment distributions;
- updating package metadata, README licensing text, generated archives,
  container metadata, and website notices where applicable;
- preserving third-party license and notice obligations under their actual
  licenses rather than describing third-party material as Apache-2.0.

There is no mixed Junjo-owned component license policy: Apache-2.0 applies
across the current platform.

## Secrets and local data

Component imports operate only on reviewed Git-tracked history. Local runtime
state, secrets, databases, caches, build output, and generated files are not
imported.

The Studio setup wizard and both deployment setup wizards may create
`.env.bak`. Before the expanded migration is implemented or either deployment
is published:

- `.env.bak` and the private atomic-writer staging pattern are explicitly
  ignored alongside `.env` in Studio and both deployment distributions;
- the generated backup is treated as secret-bearing local state;
- validation proves it cannot enter a release archive or distribution mirror.

## CI and validation boundaries

- Python SDK changes run Python validation and affected telemetry conformance.
- Studio changes run backend, frontend, ingestion, Compose, image, and affected
  telemetry validation.
- deployment changes render Compose, test setup behavior, validate version and
  environment contracts, and run appropriate smoke tests.
- website changes run its independent install, static checks, build, and link
  validation.
- contract changes run every affected producer and consumer.
- root integration checks remain small and explicit.

No root package manager or universal lock is introduced.

## Consequences

Positive consequences:

- SDK, Studio, deployment, website, and contract changes can be reviewed
  atomically when they are genuinely coupled;
- supported Studio deployments cannot silently drift from released images;
- public product terminology and links can change with their implementation;
- operators retain small cloneable deployment repositories;
- future SDKs have a clear independent home and conformance target;
- all Junjo-owned source has one clear license.

Costs and constraints:

- CI and release routing must remain precise;
- one-way distribution publication requires protected credentials and explicit
  failure handling;
- the website and Studio keep independent deployment environments;
- imported history increases repository size;
- archived repositories, hosting settings, template settings, secrets, and
  environments still require operator cutover outside source commits.

## Rejected alternatives

- Separate canonical deployment repositories: rejected because their versions,
  environment contracts, and runtime topology are owned by Studio releases.
- Removing standalone deployment repositories: rejected because a small
  cloneable operator artifact is valuable even when it is not the canonical
  source.
- Bidirectional synchronization: rejected because it creates conflicting
  sources of truth.
- Putting supported deployment distributions at repository root: rejected
  because Studio owns their runtime and release contract.
- Merging website dependencies with the Studio frontend or a root JavaScript
  workspace: rejected because they are independent deployables.
- Git submodules: rejected because they do not provide atomic contract changes
  or shared pull-request validation.
- One root package manager, version, or lock: rejected because independently
  deployable products have separate runtime and release concerns.
- Direct Studio dependency from SDKs: rejected because telemetry is the
  intended integration boundary.
