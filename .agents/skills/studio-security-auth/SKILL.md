---
name: studio-security-auth
description: Use when changing or reviewing Junjo AI Studio API-key authentication, browser sessions, internal authentication gRPC, secret handling, or another security-sensitive authentication boundary.
---

# Studio Security Auth

## Use This Skill When

- The task changes or reviews API-key validation.
- The task changes or reviews browser sessions, the session cookie, or the
  order of authentication layers.
- The task changes or reviews internal authentication gRPC between the backend
  and ingestion.
- The user asks for a security review of authentication-sensitive code.

## Do Not Use This Skill When

- The task is ordinary subsystem work with no authentication or security
  impact.
- The task merely lives near authentication code without changing the trust
  boundary.

## Surface To Inspect

- `apps/studio/backend/server/src/app.rs`
- `apps/studio/backend/server/src/config.rs`
- `apps/studio/backend/server/src/features/auth/`
- `apps/studio/backend/server/src/features/evaluation_tokens/` (developer
  access tokens and the bearer authorizer in `access.rs`)
- `apps/studio/backend/server/src/features/cli_sign_in/` (the CLI's browser
  sign-in: two public routes and three session routes)
- `apps/studio/backend/server/src/features/internal_auth.rs`
- `apps/studio/ingestion/src/server/auth.rs`
- `apps/studio/ingestion/src/backend/client.rs`
- `apps/studio/proto/auth.proto`
- `tooling/scripts/provision_local_studio.py`
- `tooling/scripts/validate_agent_studio_e2e.py`

## Workflow

1. Read `apps/studio/AGENTS.md` and
   `apps/studio/docs/adr/012-studio-authentication.md`, which owns the
   credential families and the session decisions. Studio ADR-009 owns
   ingestion API-key validation.
2. Trace the full trust boundary: caller, credential transport, cache, layer
   or extractor, backend validation, and failure mode.
3. Verify fail-closed behavior where it matters.
4. Prefer concrete threat-model checks over generic security filler.
5. Inspect active configuration and layers when deployment rules matter.
6. Pair with `studio-backend-rust` or `studio-ingestion-flow` when the change
   crosses those subsystem boundaries.
7. Local E2E users are explicit setup-API actions, never runtime or schema
   seeds. `apps/studio/TESTING.md` owns reset and validation procedures.
8. For repository-local stack setup, persistent development credentials, or
   example environment preparation, use `junjo-local-development` and its
   owning runbook.

## Validation

- Run the smallest relevant backend or integration tests.
- Prioritize the tests in `apps/studio/backend/server/src/app.rs`,
  `apps/studio/backend/server/src/features/auth/`,
  `apps/studio/backend/server/src/features/internal_auth.rs`, and
  `apps/studio/backend/server/src/config.rs`.
- One test in `app.rs` fails for any route that answers a request without a
  credential, unless the route is in that test's public list. Add a route to
  that list only on purpose.
- Validate both backend and ingestion when behavior crosses that boundary.

Authentication behavior remains owned by code and tests. Transport contracts
remain owned by proto and active service code.
