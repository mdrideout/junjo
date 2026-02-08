---
name: prepare
description: Prepare to work in the Junjo AI Studio repo by reviewing core docs (README, AGENTS, ADRs, testing/db docs, docker-compose/Dockerfiles, GitHub workflows) and then confirming readiness with a brief explanation of the system data flow. Use when starting a new task in this codebase, onboarding, or when asked to “prepare”, “review conventions/architecture”, or “understand how the system works” before making changes.
---

# Prepare for a Junjo AI Studio task

## Review core documents

1. Review `README.md`.
2. Review `AGENTS.md` (architecture overview).
3. Review global ADR docs in `docs/adr/**`.
4. Review ingestion ADR docs in `ingestion/adr/**`.
5. Review detailed docs as needed:
   - `TESTING.md` (contract tests, MSW integration tests, fixtures)
   - `backend/app/db_sqlite/README.md` (SQLite + Alembic patterns, autouse fixtures)
6. Review `docker-compose.yml` and each service Dockerfile:
   - `ingestion/Dockerfile`
   - `frontend/Dockerfile`
   - `backend/Dockerfile`
7. Skim `.github/workflows/**` to understand CI expectations (tests, proto staleness, gitleaks).

## Notes

- Do not include simulated secrets (example API keys, tokens, or credentials) in any output, including plans and comments (avoid triggering gitleaks). 

## Confirm readiness

- State that you are ready to proceed.
- Give a very short (1–3 sentence) explanation of the end-to-end data flow and functionality.

