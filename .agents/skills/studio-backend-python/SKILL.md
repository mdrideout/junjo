---
name: studio-backend-python
description: Use when changing or reviewing Junjo AI Studio FastAPI routes, backend services, repositories, SQLite patterns, DataFusion orchestration, backend API contracts, tests, or code organization.
---

# Studio Backend Python

## Use This Skill When

- The task touches `apps/studio/backend/app/`,
  `apps/studio/backend/migrations/`, or `apps/studio/backend/conftest.py`.
- The task changes FastAPI endpoints, Pydantic schemas, services,
  repositories, SQLite usage, DataFusion orchestration, or backend-visible
  ingestion query behavior.
- The task changes backend tests, scripts, or organization.

## Do Not Use This Skill When

- The task is primarily ingestion runtime flow work.
- The task is primarily frontend UI or state work.
- The task is primarily an authentication review better handled by
  `studio-security-auth`.

## Workflow

1. Read `apps/studio/AGENTS.md`, then start from the touched code and nearest
   tests.
2. Use owner docs only where they constrain the work:
   - `apps/studio/backend/app/db_sqlite/README.md`
   - `apps/studio/TESTING.md`
   - `apps/studio/ingestion/adr/002-sqlite-metadata-index.md` for indexing and
     recent-cold bridge invariants
   - `apps/studio/ingestion/adr/001-segmented-wal-architecture.md` for hot
     snapshot or WAL semantics
   - `apps/studio/docs/adr/004-events-json-contract.md` for `events_json`
3. Keep backend code explicit and single-purpose.
4. Follow the scoped runtime rules: no legacy fallbacks and no hand-edited
   Alembic migrations.
5. Pair with `studio-ingestion-flow` when changing query bridging, proto
   contracts, or hot-snapshot behavior.
6. Pair with `studio-security-auth` when changing an authentication trust
   boundary, middleware order, cookie policy, or API-key validation.
7. Keep ADRs strategic and update the owning document only.
8. Never access a running backend container's bind-mounted SQLite database or
   WAL from a host process. `apps/studio/TESTING.md` owns the stopped-stack
   reset procedure.

## Validation

Run the smallest relevant checks from `apps/studio`:

- `./backend/scripts/run-backend-tests.sh`
- `cd backend && uv run ruff check app/`
- `./backend/scripts/validate_rest_api_contracts.sh` when REST contracts change

Regenerate OpenAPI and proto artifacts through their owning scripts rather
than editing generated outputs.
