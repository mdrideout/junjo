---
name: studio-docs-sync
description: Use when auditing Junjo AI Studio docs or repo-local skills against code, cleaning ADR drift, or updating strategic documentation after implementation changes.
---

# Studio Docs Sync

## Use This Skill When

- The task reviews Studio documentation or skills for drift.
- The task updates Studio documentation after implementation changes.
- The task rationalizes ownership among ADRs, agent guidance, READMEs, and
  near-code documentation.

## Ownership

- Code and tests own implementation behavior.
- ADRs own decisions, reasoning, and consequences.
- `AGENTS.md` files provide concise runtime routing and mandatory constraints.
- Skills provide task workflow and point to owners; they are not parallel
  architecture manuals.
- READMEs provide human onboarding and links to deeper owners.

## Workflow

1. Inventory the active owners before drawing conclusions:
   - root and scoped `AGENTS.md` files
   - repo-local skills under `.agents/skills/`
   - Studio ADRs under `apps/studio/docs/adr/` and
     `apps/studio/ingestion/adr/`
   - near-code docs such as `apps/studio/TESTING.md` and
     `apps/studio/backend/app/db_sqlite/README.md`
2. Start from current code and tests.
3. Check for stale file references, contradictory decisions, duplicated
   sources of truth, runtime defaults copied into prose, and implementation
   details in the wrong document.
4. Report first when the request is an audit.
5. When editing, update the owning document and use links elsewhere. Do not
   patch the same explanation into several files.

## Validation

- Re-read changed docs and skills for duplication and contradictions.
- Verify every referenced path and command against the repository.
- Verify that linked ADRs still exist and own the stated decision.
- Keep Studio ADRs decision-level and skills workflow-level.
