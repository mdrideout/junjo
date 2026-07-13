# ADR 0001: Junjo platform monorepo

- Status: Accepted
- Date: 2026-07-12
- Owners: Junjo platform

## Context

The Junjo Python SDK and Junjo AI Studio were developed in separate Git
repositories. Agent execution will add coordinated changes to SDK lifecycle
telemetry, ingestion preservation, backend queries, frontend diagnostics, and
shared conformance fixtures. Separate repositories turn each contract change
into a manually coordinated sequence of commits and releases.

The components nevertheless have different users, dependency graphs, runtime
responsibilities, versions, licenses, and deployment artifacts. Combining
their source must not combine those boundaries.

## Decision

The existing `junjo` repository is the Junjo platform monorepo.

- Python SDK source, tests, examples, package metadata, and public docs live in
  `sdks/python`.
- Junjo AI Studio lives in `apps/studio` with its backend, frontend, ingestion
  service, internal protobufs, deployment files, and component ADRs intact.
- language-independent telemetry contracts live in `contracts/telemetry`.
- cross-platform ADRs and roadmaps live in root `docs`.
- active CI and release workflows live in root `.github/workflows` and route by
  changed path or namespaced release tag.

Each component keeps an independent dependency lock, build, version, release,
and runtime. The monorepo creates one review and compatibility boundary; it
does not create a shared application runtime.

## Runtime boundaries

- SDKs may emit the shared telemetry contract but may not import Studio code.
- Studio consumes OpenTelemetry and shared fixtures but may not import an SDK
  implementation.
- Studio-internal gRPC protobufs remain in `apps/studio/proto`; they are not the
  public cross-language telemetry contract.
- shared contract directories contain schemas and conformance data, not SDK or
  Studio business logic.
- future SDKs own their language-native dependencies and implementations while
  conforming to the same observable semantics.

## Versions and releases

Versions remain independent:

- `sdk-python-v<version>` routes only to the Python package release.
- `studio-v<version>` routes only to the Studio image release.
- future SDKs use `sdk-<language>-v<version>`.
- the telemetry contract uses its own integer version in
  `contracts/telemetry/VERSION`.

Release workflows must verify the exact namespaced tag against the component's
version before obtaining publishing credentials. A release for one component
must leave every other publisher skipped.

Historical Junjo tags remain unchanged. Imported Studio tags are namespaced as
`studio-v<original-tag>` so they cannot collide with historical Junjo tags and
follow the new Studio convention.

## Telemetry contract ownership

`contracts/telemetry` is the canonical owner of current interoperability
fixtures and schemas. A semantic change requires one atomic change containing:

1. an explicit contract-version decision
2. updated schemas and canonical fixtures
3. affected SDK emitter assertions
4. affected Studio ingestion, backend, and frontend assertions
5. documentation of the compatibility change

Product versions must not be used as an implicit contract identifier.
Every Junjo executable span carries the integer
`junjo.telemetry.contract_version` so stored and live telemetry remain
self-describing even when SDK and Studio product versions differ.

## Git history

The Python history stays in place and normal Git renames preserve file
discoverability. Studio `master` history and tags were rewritten only in a
disposable clone so every tracked Studio path is nested under `apps/studio`,
then merged without squashing and with unrelated histories explicitly allowed.
The existing public Junjo history was not rewritten.

Only Studio `master` ancestry and release tags are imported. Unmerged inactive
branch tips remain available in the archived Studio repository; they are not
part of the platform's active history. The exact source revisions and commands
are recorded in `docs/roadmaps/MONOREPO_MIGRATION_RECORD.md`.

## Licensing

Licensing is component-scoped:

- the Python SDK is Apache-2.0 under `sdks/python/LICENSE`;
- root platform documentation and shared interoperability artifacts are
  Apache-2.0 under root `LICENSE`;
- Studio remains AGPL-3.0 under `apps/studio/LICENSE`.

The root Apache license does not replace or override Studio's AGPL license.

## Consequences

Positive consequences:

- SDK and Studio compatibility changes can be reviewed and tested atomically;
- canonical fixtures have one owner;
- Agent telemetry can evolve with its diagnostic consumers;
- future SDKs have a clear independent home and conformance target;
- path-scoped CI avoids one universal dependency environment.

Costs and constraints:

- repository history is larger because both useful histories are retained;
- CI and release routing must remain precise;
- contributors must run commands from the owning component;
- GitHub issues, secrets, environments, and archived-repository settings still
  require operator cutover outside the source tree.

## Rejected alternatives

- Git submodules: rejected because they do not provide atomic cross-contract
  changes or shared pull-request validation.
- One root package manager and lock: rejected because the components are
  independent products with incompatible runtime and release concerns.
- Squashed Studio import: rejected because it destroys useful provenance.
- Direct Studio dependency from SDKs: rejected because telemetry is the
  intended integration boundary.
