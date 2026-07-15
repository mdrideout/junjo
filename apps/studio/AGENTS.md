# Junjo AI Studio AGENTS.md

Note: this directory is the Junjo AI Studio component of the Junjo platform
monorepo. It pairs through explicit telemetry contracts with the Python SDK in
`/Users/matt/repos/junjo/sdks/python`. Run Studio commands from
`/Users/matt/repos/junjo/apps/studio` unless a command says otherwise.

## Developer Philosophy

- Be grug brained.
- Everything here is greenfield. No fallbacks, deprecations, or backward compatibility are required. Do not carry through baggage when we are refactoring.
  - Breaking changes are okay, but you need to document when they are made so we can ensure the junjo sdk library remains compatible.
- Do thorough, complete work. Do not try to save time. Do not do bandaids. Do proper complete well architected work.
- Do not use abstractions unless repetition has become brittle.
- Use single responsibility principle and separation of concerns.
- No clever code. Use principle of least astonishment. No misdirection. Write simple, explicit code.
- Ground all plans, strategy, and analysis in the code. Do not make assumptions about what is in files.
- Avoid scope creep - do not re-write or change code that is not within the scope of the task unless it is directly related.

## Runtime Rules

- Never hand-edit Alembic migrations. Migrations must be generated programmatically.
- Never run migration generation yourself. Always check how this codebase runs migrations.
- Check ADR documents before implementation, and raise concerns if we are changing or violating architectural principles. Do not simply change ADRs to match new implementation without explicit consideration and approval. Implementation should follow ADR guidance as the source of strategic truth. If we change strategy, ADRs are updated before implementation proceeds. 
- When implementation details and docs disagree, trust the latest code implementation, then fix documentation drift. Raise alarms if code implementation has significant mismatch from ADRs or docs.

## Codebase Complexity

- This is a complex data ingestion + data exploration user interface repository. Changes are very likely to impact several systems.
- When planning and making changes, always investigate the end-to-end impact and downstream effects.

### Repository Domain Organization

Careful consideration is needed for code in every domain. We separate code by responsibility, however, each of these areas has contracts and interactions with each other.

- `backend/`: FastAPI backend, SQLite user DB, metadata DB, DataFusion query layer, backend tests and migrations.
- `ingestion/`: Rust OTLP ingestion service, WAL, Parquet flush, hot snapshot, ingestion ADRs and tests.
- `frontend/`: React app, Redux Toolkit state, Zod schemas, Vitest/MSW tests.
- `proto/`: Shared protobuf contracts for backend and ingestion.
- `deployments/minimal/`: Canonical source for the minimal Studio distribution
  published to `mdrideout/junjo-ai-studio-minimal-build`.
- `deployments/vm-caddy/`: Canonical source for the VM/Caddy distribution
  published to `mdrideout/junjo-ai-studio-deployment-example`.
- `docs/adr/`: Repo-wide strategic decisions and cross-service contracts only.
- `scripts/`: Root helper scripts.

The two standalone deployment repositories are generated, one-way release
mirrors. Change and review deployment source here; direct mirror changes will
be overwritten by the next publication.

## Important Commands

Run from the Studio root (`apps/studio`) unless a command says otherwise.

- Full stack: `docker compose up -d`
- Full test suite: `./run-all-tests.sh`
- Python proto generation: `./run-all-proto-gen.sh`

Backend:

- All backend tests: `./backend/scripts/run-backend-tests.sh`
- Backend contract validation: `./backend/scripts/validate_rest_api_contracts.sh`
- Backend lint: `cd backend && uv run ruff check app/`

Frontend:

- Frontend tests: `cd frontend && npm run test:run`
- Frontend lint: `cd frontend && npm run lint`
- Frontend build: `cd frontend && npm run build`

Ingestion:

- Ingestion tests: `cd ingestion && cargo test --locked`

Deployments:

- Validate the Compose configuration and setup-script dry runs from each
  changed directory under `deployments/`.
- Validate generated archives and mirror equivalence before publishing a
  Studio release.

## Documentation Rules

Do not create duplicate sources of truth in documentation. Make sure documentation has a proper owner. You can reference other docs from a document, but never have duplication of content. 

- `AGENTS.md`: Repo runtime guidance for Codex. Keep it short and practical.
- `.agents/skills/`: Detailed subsystem or workflow instructions for repeated tasks.
- `README.md`: Human onboarding and product/developer overview.
- `docs/adr/`: Global level ADRs (individual features may have their own ADR docs)
- `ingestion/adr/`: Ingestion-owned design decisions only.
- `TESTING.md`: Human testing guide.
- `backend/app/db_sqlite/README.md`: Backend DB subsystem guidance.

ADRs are for decisions made, architecture, strategy, reasoning, alternatives evaluated, and providing context for why things are the way they are. They make it clear what the latest implementation is, and briefly mention past implementations or declined implementations. These help humans and LLMs avoid re-introducing faulty logic or making changes inconsiderate of important decisions.

- When working in a directory, always check it for ADR docs.
- Implementation belongs in code and tests. We do not duplicate implementation details in docs.
- Do not write code in docs. Docs are higher level, strategic, or pseudo-code.

## Skills

Utilize skills during implementation and plannning. AGENTS.md is for context that should be in EVERY runtime agent process. Skills are domain or task specific.

- `ingestion-flow`: WAL, flush, snapshot, recent-cold bridging, OTLP ingestion, ingestion-related proto work.
- `backend-python`: FastAPI, backend repositories/services, SQLite patterns, DataFusion orchestration, backend tests.
- `frontend-react`: React architecture, Redux Toolkit patterns, frontend schemas, frontend tests.
- `security-auth`: API keys, session cookies, CORS, internal auth gRPC, security-sensitive reviews.
- `docs-sync`: Docs drift audits, ADR cleanup, source-of-truth checks, report-first doc work.

## Nested Instructions Policy

- Do not add nested `AGENTS.md` or `AGENTS.override.md` files unless working in that directory truly requires a different rule set every time.
- Prefer a skill over a nested `AGENTS.md` when the specialization is task-based rather than directory-enforced.

## Repo Config Policy

- Do not add repo `.codex/config.toml` unless the repo needs durable Codex behavior that does not belong in `AGENTS.md` or a skill.
- Do not copy personal defaults from `~/.codex/config.toml` into the repo.

## Change Hygiene

- Check the worktree before destructive edits.
- Do not revert unrelated user changes.
- Changes to telemetry projections, Workflow selection, Mermaid rendering,
  execution-detail routing, or the frontend dependency lock must run the
  Workflow Graph/tree/state/URL interaction suite. Review transitive renderer
  changes as behavior changes, not mechanical lockfile noise.
- Before changing a shared selection or detail contract, inventory every
  surface that projects it, including deep links and mixed Agent/Workflow
  composition.
- During procedural tasks, keep track of mistakes made (CLI misuse, etc.) and document what the correct implementation was to help future task runners avoid the same issue.
