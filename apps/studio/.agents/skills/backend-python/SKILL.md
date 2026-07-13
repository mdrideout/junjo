---
name: backend-python
description: Use when changing or reviewing FastAPI routes, backend services, repositories, SQLite patterns, DataFusion orchestration, backend-visible ingestion query behavior, backend API contracts, backend tests, or backend code organization. Owns Python backend architecture, not ingestion internals or frontend architecture.
---

# Backend Python

## Use This Skill When

- The task touches `backend/app/`, `backend/migrations/`, or `backend/conftest.py`.
- The task changes FastAPI endpoints, Pydantic schemas, services, repositories, SQLite usage, DataFusion orchestration, or backend-visible ingestion query behavior.
- The task changes backend tests, backend scripts, or backend code organization.

## Do Not Use This Skill When

- The task is primarily ingestion runtime flow work in `ingestion/`.
- The task is primarily frontend UI or state work in `frontend/`.
- The task is primarily auth/session/security review better handled by `security-auth`.

## Owned Paths

- `backend/app/`
- `backend/migrations/`
- `backend/conftest.py`
- `backend/scripts/`

## Workflow

1. Start from the touched code paths and nearest tests.
2. Use owner docs and ADRs only where they constrain the backend work:
   - `backend/app/db_sqlite/README.md`
   - `TESTING.md`
   - `ingestion/adr/002-sqlite-metadata-index.md` for file-selection, indexing, and recent-cold bridge invariants
   - `ingestion/adr/001-segmented-wal-architecture.md` when backend logic depends on hot snapshot or WAL semantics
   - `docs/adr/004-events-json-contract.md` when changing `events_json` pass-through or backend assumptions about event payload shape
3. Keep backend code explicit and single-purpose.
4. Follow the repo runtime rules:
   - no fallback logic for legacy behavior
   - no hand-edited Alembic migrations
   - ask the user to generate migrations when schema changes require them
5. If the task changes query bridging, proto contracts, or hot-snapshot behavior, pair this skill with `ingestion-flow`.
6. If the task changes an auth trust boundary, middleware order, cookie policy, or API key validation behavior, pair this skill with `security-auth`.
7. Keep ADRs strategic. If a backend change requires doc updates, update the owning doc rather than restating implementation details in multiple places.

## Validation Expectations

- Run the smallest relevant backend verification:
  - `./backend/scripts/run-backend-tests.sh`
  - `cd backend && uv run ruff check app/`
  - targeted pytest commands when appropriate
- If REST API contracts changed, run `./backend/scripts/validate_rest_api_contracts.sh`.
- If OpenAPI or proto outputs are affected, regenerate through the owning script instead of editing outputs directly.

## Source Of Truth Rules

- Backend behavior lives in code and tests.
- `backend/app/db_sqlite/README.md` is backend DB guidance, not root `AGENTS.md`.
- Backend-visible ingestion constraints live in the owning ingestion ADRs plus active backend and ingestion code, not in duplicated backend prose.
- `docs/adr/` should contain decisions, not backend implementation walk-throughs.
