# Junjo Platform AGENTS.md

Junjo is a multi-component platform repository. Read this file first, then read
the nearest scoped `AGENTS.md` before changing a component.

## Developer philosophy

- Be grug brained: prefer simple, explicit code and contracts.
- Everything is greenfield. Intentional breaking changes are allowed, but they must be documented and coordinated across every affected component.
- Do complete, well-architected work. Do not add compatibility fallbacks or abstractions that hide ownership.
- Follow single responsibility and separation of concerns.
- Ground plans and reviews in current code and accepted ADRs.
- Avoid scope creep and preserve unrelated user work.
- Do not engage in scope creep. Do not take liberties to refactor or change things that do not need to change beyond the requested implementations and ideas. Keep existing user-interfaces, styles, contracts, integrations, system -> system mechanics as they are unless it's required to change them as part of new feature implementation. Keep changes necessary and required. As much as needed, as little as possible.

## Scope and Complexity

Simplicity is valuable. The more complex we make the systems, the more edge cases for issues there are, the more testing we need to do, the more brittle the system becomes, and the higher the blast radius of all future changes. This is why we avoid scope increases and complexity and avoid these problems.

We do not need to mitigate or handle all exceptions at all costs. Allowing exceptions to happen especially for very rare or transient circumstances is better than creating complexity and architecture changes to accommodate a very rare or temporary situations.

- Keep work in-scope. If increased scope is recommended, provide it as a note to the developer after completing the task.
- Do not follow tangents and rabbit holes. Build on the critical path to feature completion. Make considerations for tangents and threads to follow after completing the critical tasks.
- You prioritize and implement work using Scrum and KANBAN. Work through the highest priority elements first. Get each piece working and done before moving on. Build iteratively. Do not try and create the whole system at once.
- Do not over-engineer solutions. Start with the working low-complexity solution and only add complexity as necessary by proven need.
- Do not change architecture or strategy to acommodate pedantic nitpicks that have low material impact.
- Race conditions and footguns must be grounded in likely real-world exceptions, NOT unlikely theoretical scenarios in a vacuum.
- Do not get caught in self-invalidation loops. This can look like failing overly-pedantic tests, over-engineering a solution to pass the test, and then failing those tests. I end up deleting a lot of these scenarios to save you and allow forward progress.

Solidify required behavior and explicit non-goals before coding. It is important to explore the surface area and any potential for recommended scope or complexity increases during planning stages so that there are no scope surprises after implementation is finished. 

Scope increases beyond the scope the user has requested should not be implemented. Stop yourself. Stay within scope. After the work is completed. Include suggested scope increases in your work report. isolate separately justified fixes into independent changes with their own evidence and blast-radius review.

Examples of bad, unauthorized scope increases due to bad implementation judgement:

- Bad: converted an accepted transient rollout edge case into a permanent compatibility architecture, causing a chain of versioned actions, legacy handlers, Replay aliases, serializers, and deployment ordering that was more complex and riskier than the requested fix.
- Bad: Expanding targeted alert hygiene into orchestration overhauls
- Bad: treating a tolerable rolling-deployment window as a permanent compatibility requirement
- Bad: generated a database migration to accommodate a slightly longer label instead of making a shorter label.

## Repository ownership

- `.agents/skills`: monorepo-visible task guidance. Skills use component
  prefixes and route back to the owning code, scoped `AGENTS.md`, and ADRs.
- `sdks/python`: Python SDK, public API, tests, source-owned docs exports, and examples. Follow
  `sdks/python/AGENTS.md`.
- `apps/studio`: Studio backend, frontend, ingestion, deployment, and internal
  contracts. Follow `apps/studio/AGENTS.md`.
- `apps/studio/deployments`: canonical source for supported Studio deployment
  distributions. Standalone deployment repositories are generated release
  mirrors and are never a second source of truth.
- `apps/website`: Astro/Starlight product and unified documentation renderer.
  It keeps its own JavaScript dependency lock; the production artifact is
  assembled from source-owned documentation exports. Follow
  `apps/website/AGENTS.md`.
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

- Python SDK: Ruff, pytest, ty, Griffe public-surface validation, package build,
  and Twine validation from `sdks/python`.
- Studio: `apps/studio/run-all-tests.sh`, plus Compose and Docker validation
  when deployment inputs change.
- Studio deployment distributions: validate Compose rendering, setup scripts,
  archive contents, and generated-mirror equivalence for every changed
  distribution.
- Website: `npm ci` and `npm run build` from `apps/website`, plus the root
  documentation assembly and parity validation when public docs inputs change.
- Shared contracts: regenerate with `python3
  contracts/telemetry/compatibility/generate_v2_fixtures.py`, validate with
  `python3 contracts/telemetry/compatibility/validate_contract.py`, prove the
  generated contract tree is unchanged, and run producer and consumer
  conformance tests.

Do not treat one component's green build as proof that a cross-component change
is compatible.
