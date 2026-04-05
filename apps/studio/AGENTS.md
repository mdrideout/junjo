# Junjo AI Studio AGENTS.md

## Repository Expectations

- Be grug brained.
- Everything here is greenfield. No fallbacks or backward compatibility are required.
- Do thorough, complete work. Do not optimize for shortcutting the task.
- Avoid abstractions unless repetition has become brittle.
- Prefer straightforward, single-purpose code.
- Prefer explicit control flow over clever code.
- Code is the source of truth. Keep docs strategic and scoped.

## Runtime Rules

- Never hand-edit Alembic migrations.
- Never run migration generation yourself.
- If a model change needs a migration, ask the user to generate it.
- Do not preserve stale docs for convenience.
- Do not introduce duplicate instruction surfaces when one owner is enough.
- When implementation details and docs disagree, trust the code, then fix the docs.

## Repo Layout

- `backend/`: FastAPI backend, SQLite user DB, metadata DB, DataFusion query layer, backend tests and migrations.
- `ingestion/`: Rust OTLP ingestion service, WAL, Parquet flush, hot snapshot, ingestion ADRs and tests.
- `frontend/`: React app, Redux Toolkit state, Zod schemas, Vitest/MSW tests.
- `proto/`: Shared protobuf contracts for backend and ingestion.
- `docs/adr/`: Repo-wide strategic decisions and cross-service contracts only.
- `scripts/`: Root helper scripts.

## Commands That Matter

Run from repo root unless a command says otherwise.

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

## Done Means

- The requested change is fully implemented end-to-end.
- The smallest relevant verification commands were run.
- Generated artifacts were updated only through the owning command or script.
- Docs were updated only in the owning document when behavior or decisions changed.
- No duplicated or stale guidance was introduced.

## Documentation Ownership

- `AGENTS.md`: Repo runtime guidance for Codex. Keep it short and practical.
- `.agents/skills/`: Detailed subsystem or workflow instructions for repeated tasks.
- `README.md`: Human onboarding and product/developer overview.
- `docs/adr/`: Decision records only. No implementation tutorials.
- `ingestion/adr/`: Ingestion-owned design decisions only.
- `TESTING.md`: Human testing guide.
- `backend/app/db_sqlite/README.md`: Backend DB subsystem guidance.

When updating docs:

- Put implementation detail in code, tests, or near-code docs.
- Put decisions in ADRs.
- Do not mirror the same design across multiple ADRs.
- Do not add file inventories or config snapshots that will drift.

## Skills Dispatch

Use repo-local skills instead of expanding this file.

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
- Prefer small, high-signal docs over long explanatory documents.
- If Codex makes the same repo-specific mistake twice, update the correct skill or this file.
