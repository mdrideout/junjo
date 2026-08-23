---
name: studio-security-auth
description: Use when changing or reviewing Junjo AI Studio API-key authentication, session cookies, CORS, internal authentication gRPC, secret handling, or another security-sensitive authentication boundary.
---

# Studio Security Auth

## Use This Skill When

- The task changes or reviews API-key validation.
- The task changes or reviews session cookies, CORS, domain requirements, or
  authentication middleware ordering.
- The task changes or reviews internal authentication gRPC between the backend
  and ingestion.
- The user asks for a security review of authentication-sensitive code.

## Do Not Use This Skill When

- The task is ordinary subsystem work with no authentication or security
  impact.
- The task merely lives near authentication code without changing the trust
  boundary.

## Surface To Inspect

- `apps/studio/backend/app/main.py`
- `apps/studio/backend/app/config/settings.py`
- `apps/studio/backend/app/features/auth/`
- `apps/studio/backend/app/features/internal_auth/`
- `apps/studio/ingestion/src/server/auth.rs`
- `apps/studio/ingestion/src/backend/client.rs`
- `apps/studio/proto/auth.proto`
- `tooling/scripts/provision_local_studio.py`
- `tooling/scripts/validate_agent_studio_e2e.py`

## Workflow

1. Read `apps/studio/AGENTS.md`. There is no dedicated authentication ADR, so
   start from current code and tests.
2. Trace the full trust boundary: caller, credential transport, cache or
   middleware, backend validation, and failure mode.
3. Verify fail-closed behavior where it matters.
4. Prefer concrete threat-model checks over generic security filler.
5. Inspect active settings and middleware when deployment rules matter.
6. Pair with `studio-backend-python` or `studio-ingestion-flow` when the change
   crosses those subsystem boundaries.
7. Local E2E users are explicit setup-API actions, never runtime or migration
   seeds. `apps/studio/TESTING.md` owns reset and validation procedures.
8. For repository-local stack setup, persistent development credentials, or
   example environment preparation, use `junjo-local-development` and its
   owning runbook.

## Validation

- Run the smallest relevant backend or integration tests.
- Prioritize `apps/studio/backend/tests/security/`,
  `apps/studio/backend/tests/test_production_settings.py`, and
  `apps/studio/backend/app/features/internal_auth/test_*.py`.
- Validate both backend and ingestion when behavior crosses that boundary.

Authentication behavior remains owned by code and tests. Transport contracts
remain owned by proto and active service code.
