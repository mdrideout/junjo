---
name: docs-sync
description: Use when auditing docs or repo-local skills against code, cleaning ADR drift, or updating strategic docs after implementation changes. This is a report-first maintenance skill: inspect, compare, identify drift, then edit the owning document only when appropriate.
---

# Docs Sync

## Use This Skill When

- The task is to review docs for drift.
- The task is to review repo-local skills for drift or incorrect ownership.
- The task is to update docs after implementation changes.
- The task is to rationalize ADR ownership or remove duplicated documentation.
- The task is to identify which document should own a given statement.

## Do Not Use This Skill When

- The task is primarily code implementation with only incidental doc touch-up.
- The task is subsystem-specific enough that one of the domain skills should lead.

## Owned Concerns

- Documentation drift detection
- Ownership boundaries between root docs, ADRs, and near-code docs
- Skill drift detection
- Report-first recommendations for doc cleanup

## Workflow

1. Inventory the active owners before drawing conclusions:
   - root docs such as `AGENTS.md`
   - repo-local skills under `.agents/skills/`
   - every ADR directory in the repo, including `docs/adr/` and `ingestion/adr/`
   - near-code docs such as `backend/app/db_sqlite/README.md` and `TESTING.md`
2. Start from the code and tests.
3. Compare docs and skills only against the current implementation and active ownership model.
4. Identify:
   - stale file references
   - duplicated decisions
   - runtime defaults copied from code
   - implementation details living in the wrong document
   - skills that claim concerns not grounded in active code or ADRs
5. Prefer reporting first when the user asks for review or audit.
6. When editing, update the owning document only. Do not patch the same explanation in multiple places.

## Validation Expectations

- After edits, re-read the changed docs and skills for duplicated or stale content.
- Check referenced paths and commands against the repo.
- If skills reference ADRs, verify that each ADR still exists and is the right owner.
- Keep ADRs decision-level, `AGENTS.md` runtime-level, and skills workflow-level.

## Source Of Truth Rules

- Code, tests, and near-code docs are the implementation source of truth.
- ADRs record decisions and consequences.
- Root docs should route readers to owners, not mirror subsystem implementation.
- Skills should point to owning code and ADRs, not become parallel architecture manuals.
