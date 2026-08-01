---
name: api-contracts
description: Use when a Studio backend endpoint is added or changed and that endpoint is consumed by the frontend, SDK, CLI, or another service. Keeps producer and consumer contracts aligned without creating a second schema authority.
---

# API Contracts

## Contract Decisions

- Backend route and Pydantic schemas own the REST contract.
- Generated OpenAPI is the transport artifact, not a hand-edited source.
- Frontend Zod schemas and request code are consumers and must change with the
  backend contract.
- Authentication, cookies, CORS, status codes, and error envelopes are part of
  the endpoint contract.
- A cross-boundary endpoint change is incomplete until its producer and every
  affected consumer are validated together.

## Surface To Inspect

- `backend/app/features/` and the owning backend tests
- `backend/scripts/export_openapi_schema.py`
- `frontend/backend/openapi.json`
- `frontend/src/features/` or `frontend/src/auth/`
- `frontend/src/__tests__/contracts/` and `frontend/src/__tests__/integration/`
- SDK or CLI clients when they call the same route

## Routing

Use `backend-python` for backend implementation, `frontend-react` for browser
implementation, and `security-auth` when the contract includes credentials,
sessions, or CORS. Validation commands remain owned by `AGENTS.md`; concrete
behavior remains owned by code and tests.
