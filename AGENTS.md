# Junjo Platform AGENTS.md

Junjo is a multi-component platform repository. Read this file first, then read
the nearest scoped `AGENTS.md` before changing a component.

## Developer philosophy

- Be grug brained: prefer simple, explicit code and contracts.
- Everything is greenfield. Intentional breaking changes are allowed, but they
  must be documented and coordinated across every affected component.
- Do complete, well-architected work. Do not add compatibility fallbacks or
  abstractions that hide ownership.
- Follow single responsibility and separation of concerns.
- Ground plans and reviews in current code and accepted ADRs.
- Avoid scope creep and preserve unrelated user work.

## Repository ownership

- `sdks/python`: Python SDK, public API, tests, docs, and examples. Follow
  `sdks/python/AGENTS.md`.
- `apps/studio`: Studio backend, frontend, ingestion, deployment, and internal
  contracts. Follow `apps/studio/AGENTS.md`.
- `contracts/telemetry`: language-independent schemas, versions, and fixtures.
- `docs/adr`: cross-platform architectural decisions.
- `docs/roadmaps`: cross-platform strategy and implementation roadmaps.
- `.github/workflows`: path-scoped CI and independently routed releases.

## Boundary rules

- A monorepo is not a shared runtime or shared dependency graph.
- SDKs must not depend on Studio runtime code.
- Studio must consume telemetry and explicit contracts, not SDK internals.
- Each deployable keeps its own lockfile, version, build, and release artifact.
- Shared contract code contains no product runtime behavior.
- Language SDKs share semantics and conformance fixtures, not mechanical source
  abstractions.

## Architectural decisions

Read the accepted ADRs for the area before implementation. Cross-platform
strategy lives in `docs/adr`; component decisions remain with the component.
Do not silently change an ADR to match an implementation. If strategy changes,
propose and approve the ADR change before implementing it.

## Cross-system contract changes

Telemetry contract changes must update together:

1. the contract version or schema when semantics change
2. canonical schemas and fixtures
3. affected SDK emitters and conformance tests
4. Studio ingestion, backend, and frontend consumers
5. public and implementation documentation

OpenTelemetry is a first-class integration boundary. Do not route telemetry
through public hooks or couple Studio to an SDK's internal lifecycle objects.

## Validation routing

Run the full validation owned by every changed area. At minimum:

- Python SDK: Ruff, pytest, ty, Sphinx, package build, and Twine validation from
  `sdks/python`.
- Studio: `apps/studio/run-all-tests.sh`, plus Compose and Docker validation
  when deployment inputs change.
- Shared contracts: `python3
  contracts/telemetry/compatibility/validate_contract.py`, plus producer and
  consumer conformance tests.

Do not treat one component's green build as proof that a cross-component change
is compatible.
