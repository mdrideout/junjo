---
name: studio-api-contracts
description: Use when a Junjo AI Studio backend endpoint is added or changed and that endpoint is consumed by the frontend, SDK, CLI, or another service.
---

# Studio API Contracts

## Contract Decisions

- Backend routes and Pydantic schemas own REST contracts.
- Generated OpenAPI is a transport artifact, not a hand-edited source.
- Frontend Zod schemas and request code are consumers and change with the
  backend contract.
- Authentication, cookies, CORS, status codes, and error envelopes are part of
  the endpoint contract.
- A cross-boundary change is incomplete until the producer and every affected
  consumer are validated together.

## Surface To Inspect

- `apps/studio/backend/app/features/` and the owning backend tests
- `apps/studio/backend/scripts/export_openapi_schema.py`
- `apps/studio/frontend/backend/openapi.json`
- `apps/studio/frontend/src/features/` or `apps/studio/frontend/src/auth/`
- `apps/studio/frontend/src/__tests__/contracts/`
- `apps/studio/frontend/src/__tests__/integration/`
- SDK or CLI clients that call the same route

## Routing

Use `studio-backend-python` for backend implementation,
`studio-frontend-react` for browser implementation, and
`studio-security-auth` when the contract includes credentials, sessions, or
CORS. Validation commands remain owned by scoped `AGENTS.md` files; concrete
behavior remains owned by code and tests.
