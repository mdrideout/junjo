---
name: security-auth
description: Use when changing or reviewing API key auth, session cookies, CORS, domain constraints, internal auth gRPC, secret handling, or any security-sensitive auth boundary. This is a cross-cutting review skill and should stay narrow to authentication and security concerns.
---

# Security Auth

## Use This Skill When

- The task changes or reviews API key validation.
- The task changes or reviews session cookies, CORS, registrable-domain requirements, or auth middleware ordering.
- The task changes or reviews internal auth gRPC behavior between backend and ingestion.
- The user asks for a security review of auth-sensitive code.

## Do Not Use This Skill When

- The task is ordinary subsystem work with no auth or security impact.
- The task is a general backend or frontend change that happens to live near auth code but does not alter the security boundary.

## Owned Concerns

- API key auth flow
- Session cookie flow
- CORS and same-domain constraints
- Internal auth gRPC boundary
- Secret handling and fail-closed behavior

## Owning Code

- `backend/app/main.py`
- `backend/app/config/settings.py`
- `backend/app/features/auth/`
- `backend/app/features/internal_auth/`
- `ingestion/src/server/auth.rs`
- `ingestion/src/backend/client.rs`
- `proto/auth.proto`

## Workflow

1. There is no dedicated auth ADR today. Start from code and tests.
2. Trace the full trust boundary before editing:
   - caller
   - credential transport
   - cache / middleware / interceptor
   - backend validation
   - failure mode
3. Verify fail-closed behavior where it matters.
4. Prefer concrete threat-model checks over broad “security best practice” filler.
5. When deployment rules matter, check the real settings and middleware code instead of relying on stale prose.
6. If the task also changes backend architecture outside the security boundary, pair this skill with `backend-python`.
7. If the task also changes ingestion-path runtime behavior, pair this skill with `ingestion-flow`.

## Validation Expectations

- Run the smallest relevant backend or integration tests for auth-sensitive changes.
- Prioritize the owner tests:
  - `backend/tests/security/`
  - `backend/tests/test_production_settings.py`
  - `backend/app/features/internal_auth/test_*.py`
- If behavior spans backend and ingestion, validate both sides of the boundary.
- Document security-sensitive reasoning in the owning code or doc, not in duplicated summaries.

## Source Of Truth Rules

- No dedicated auth ADR currently exists; auth guidance is code-first in the active code and tests.
- Middleware order and settings live in backend code.
- Auth transport contracts live in `proto/` and active service code.
- Security constraints in docs must remain strategic and current.
