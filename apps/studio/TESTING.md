# Testing Guide

This document covers testing patterns and practices for Junjo AI Studio.

## Table of Contents

1. [Running Tests](#running-tests)
2. [Local Agent E2E Identity](#local-agent-e2e-identity)
3. [Testing Strategy Overview](#testing-strategy-overview)
4. [Platform Telemetry Contract](#platform-telemetry-contract)
5. [Workflow Execution Exploration](#workflow-execution-exploration)
6. [Contract Testing (Frontend/Backend)](#contract-testing-frontendbackend)
7. [Integration Testing with MSW](#integration-testing-with-msw)
8. [Shared Test Fixtures](#shared-test-fixtures)
9. [Common Testing Pitfalls](#common-testing-pitfalls)
10. [Backend Test Markers](#backend-test-markers)

---

## Running Tests

### Backend Tests (All Tests)

Run the complete backend test collection, including security, concurrency, and
gRPC integration tests:

```bash
cd backend
./scripts/run-backend-tests.sh
```

**What it does:**
- Runs the complete pytest collection once, including unmarked semantic and query tests
- Includes unit, integration, security, concurrency, error-recovery, and gRPC tests
- Uses pytest fixtures for isolated databases and the in-process gRPC service

**Why use this script:**
- Ensures all backend tests pass before committing
- Handles cleanup of temporary database files
- Validates that port 50053 is free before running gRPC tests

### Frontend Tests

Run all frontend tests:

```bash
cd frontend
npm run test:run
```

Use `npm test` only when you want Vitest watch mode.

The complete Studio runner also executes frontend lint and the production
TypeScript/Vite build:

```bash
./run-all-tests.sh
```

**What it covers:**
- Contract tests (Zod schemas vs OpenAPI)
- Integration tests (MSW request validation)
- Component tests (React components)
- Utility tests (pure functions)

### Quick Test Commands

**Backend - Skip gRPC tests (normal development):**
```bash
cd backend
uv run pytest -m "not requires_grpc_server" -v
```

**Backend - Run specific category:**
```bash
uv run pytest -m unit              # Unit tests only
uv run pytest -m integration       # Integration tests only
uv run pytest -m security          # Security tests only
```

---

## Local Agent E2E Identity

The local default user is created through Studio's public first-user setup API,
the same contract used by the setup form. It is not a database seed and is
never created by startup, Compose, migrations, or a build:

- Email: `admin@test.com`
- Password: `JunjoAIStudioLocalTestPass1!`

For a greenfield local proof, stop the stack before removing its bind-mounted
data, then restart Studio and run either live validator:

```bash
docker compose down --volumes --remove-orphans
rm -rf .dbdata
mkdir -p .dbdata
docker compose up --build --detach
```

Create the empty shared root before Compose starts. This avoids making the
backend and ingestion containers race to create the same bind-mount root on a
warm local rebuild.

The validator asks Studio whether setup is required and, only on an empty
deployment, submits `admin@test.com` through `/users/create-first-user`. It uses
a separate random user and credentials for the proof, removes those disposable
records through the HTTP API, and finishes by signing the retained owner out
and back in. Existing-user distribution tests supply paired credentials through
`JUNJO_STUDIO_E2E_EXISTING_EMAIL` and `JUNJO_STUDIO_E2E_EXISTING_PASSWORD`.

The running containers exclusively own the SQLite database and its WAL files.
Never open, query, or modify the bind-mounted SQLite files from the host while
Studio is running. Use Studio's HTTP APIs for live validation; stop the entire
stack before a greenfield wipe or offline database maintenance.

### Persistent Local Development Credentials

After Studio is running in development mode, provision the retained local
owner, one Application Telemetry API Key, one Developer Access Token, and the
ignored environment files used by the repository examples:

```bash
cd ../..
python3 tooling/scripts/provision_local_studio.py
```

Run the command from the repository root. It accepts only the repository-local
loopback backend and stops unless Studio reports `development`. It creates the
owner only through the public first-user setup contract, then creates or reuses
these authenticated Studio records:

- `Local Development Application Telemetry`
- `Local Development Developer Access`

The access token has evaluation read/write and evidence-read authority with no
expiration. The provisioner writes the resulting credentials and local Studio
endpoints to the ignored `.env` files for AI Chat, the base OpenAI Agents
integration, and the base SDK example. Existing provider credentials and other
unrelated settings are preserved. Templates are never modified, and canonical
credential values are never printed.

The command is idempotent: ordinary restarts and repeated provisioning reuse
the exact named records. A greenfield `.dbdata` wipe removes those records, so
rerun the provisioner afterward to create new credentials and update the
example environments.

These persistent credentials are for local human and coding-agent iteration.
Live validators continue to create and delete their own disposable users and
credentials so automated proofs remain isolated. See the example-owned setup
and run instructions:

- [AI Chat](../../sdks/python/examples/ai_chat/README.md)
- [Base OpenAI Agents integration](../../sdks/python/examples/base_openai_agents/README.md)
- [Base SDK example](../../sdks/python/examples/base/README.md)

---

## Testing Strategy Overview

### Testing Decision Tree

**What are you testing?**
- **API response structure?** → Contract Test
  *Does Zod schema match OpenAPI?* → `__tests__/contracts/mutation-contracts.test.ts`

- **Request payload structure?** → Integration Test
  *Does fetch() send correct data?* → `__tests__/integration/mutation-requests.test.ts`

- **Component behavior?** → Component Test
  *Render, user interactions* → `Component.test.tsx` (co-located)

- **Utility function?** → Unit Test
  *Pure logic, no dependencies* → `utils/helper.test.ts`

- **Multiple features together?** → Integration Test

- **Complete user flow?** → End-to-End Test

### Test Coverage Guidelines

- **Contract tests:** Every API endpoint (GET, POST, PUT, DELETE)
- **Integration tests:** All mutation operations with path/body parameters
- **Component tests:** All user-facing components with interactions
- **Unit tests:** All utility functions and business logic

---

## Platform Telemetry Contract

Language-independent telemetry schemas and normalized Workflow fixtures live
at `../../contracts/telemetry`. They are the compatibility boundary between SDK
emitters and Studio ingestion, backend, and frontend consumers; do not fork
component-local copies.

From the platform root, validate the canonical artifacts with:

```bash
python3 contracts/telemetry/compatibility/validate_contract.py
```

Backend and frontend transport tests load the same files from
`contracts/telemetry/fixtures/workflow`. A semantic telemetry change must update
the contract version or schema as appropriate and keep all producer and
consumer tests green in one change.

---

## Workflow Execution Exploration

Workflow detail is one interaction across the Graph, nested span tree, Store
transition list, state projection, detail panel, and URL. A change to any one
surface must preserve the matrix in Studio ADR-008.

| Behavior | Test owner |
| --- | --- |
| Graph snapshot to span matching, including Agent ancestry | `src/mermaidjs/junjo-graph-span-matching.test.ts` |
| Installed Mermaid DOM to Junjo identity | `src/mermaidjs/mermaid-dom-adapter.test.ts` |
| Graph click and selected-span highlight | `src/mermaidjs/RenderJunjoGraphMermaid.test.tsx` |
| Route restoration and cross-Workflow reset | `src/features/junjo-data/workflow-detail/WorkflowDetailPage.test.tsx` |
| Store sequence and previous/next selection | `src/features/junjo-data/workflow-detail/WorkflowStoreTransitionNavigation.test.tsx` |
| Pending semantic link becoming resolved content | `src/features/execution-resolution/ExecutionResolverPage.test.tsx` |
| Store status presentation | `src/features/workflow-executions/components/WorkflowStoreDiagnosticsNotice.test.tsx` |

The Mermaid adapter test must call the actual installed Mermaid renderer. A
fixture containing hand-authored legacy SVG IDs is insufficient. Cover normal
nodes, RunConcurrent clusters, Subflow parent/child Graphs, unexecuted nodes,
edge-label rerendering, and a model or Agent span nested inside a Workflow Node.

When `package-lock.json` changes, review Mermaid and its renderer dependencies
even if `package.json` did not change. Run the complete frontend tests, lint,
and production build after any renderer or selection change.

---

## Contract Testing (Frontend/Backend)

### Philosophy

**Backend Pydantic schemas are the single source of truth.**

Frontend Zod schemas are validated against backend OpenAPI schemas to ensure compatibility. This catches breaking changes before they reach production.

### How It Works

1. **Backend adds examples** to Pydantic response schemas:
   ```python
   class UserRead(BaseModel):
       id: str = Field(examples=["usr_2k4h6j8m9n0p1q2r"])
       email: str = Field(examples=["user@example.com"])
       created_at: datetime = Field(examples=[datetime.now(UTC)])
   ```

2. **Export OpenAPI schema:**
   ```bash
   uv run python scripts/export_openapi_schema.py
   ```

3. **Frontend contract tests** validate Zod schemas can parse OpenAPI-generated mocks:
   ```typescript
   import { generateMock } from '@/auth/test-utils/openapi-mock-generator'
   import { ListUsersResponseSchema } from '@/users/schemas'

   describe('API Contract: UserRead Schema', () => {
     it('Zod schema can parse OpenAPI-generated mock', () => {
       const { mock } = generateMock('list_users_users_get')
       const result = ListUsersResponseSchema.parse(mock)
       expect(result).toBeDefined()
     })
   })
   ```

### What Contract Tests Catch

| Change | What Happens |
|--------|-------------|
| Backend adds required field | ❌ Zod parse fails (missing field) |
| Backend changes field type | ❌ Zod parse fails (type mismatch) |
| Frontend has wrong field name | ❌ Zod parse fails (unknown field) |
| Backend removes optional field | ✅ Test passes (optional fields OK) |
| Backend changes field name | ❌ Zod parse fails (missing field) |

### Path Parameter Type Validation

**Critical:** Validate path parameter types to prevent string vs number bugs:

```typescript
describe('API Contract: DELETE /users/{user_id}', () => {
  it('user_id parameter is defined as string', () => {
    const operation = api.getOperation('delete_user_users__user_id__delete')
    const userIdParam = operation?.parameters?.find((p) => p.name === 'user_id')

    expect(userIdParam).toBeDefined()
    expect(userIdParam?.schema?.type).toBe('string')
  })
})
```

**Why this matters:** Common bug is treating string IDs as numbers. This test ensures backend schema matches frontend expectations.

### Contract Test Example (Complete)

```typescript
// frontend/src/__tests__/contracts/user-contracts.test.ts
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { initOpenAPI, generateMock } from '@/auth/test-utils/openapi-mock-generator'
import { UserReadSchema, ListUsersResponseSchema } from '@/users/schemas'

beforeAll(async () => {
  await initOpenAPI()
})

describe('User API Contracts', () => {
  it('UserRead schema matches OpenAPI', () => {
    const { mock } = generateMock('get_user_users__user_id__get')
    const result = UserReadSchema.parse(mock)
    expect(result).toBeDefined()
    expect(result.id).toBeDefined()
    expect(result.email).toBeDefined()
  })

  it('ListUsers response schema matches OpenAPI', () => {
    const { mock } = generateMock('list_users_users_get')
    const result = ListUsersResponseSchema.parse(mock)
    expect(Array.isArray(result)).toBe(true)
  })
})
```

---

## Integration Testing with MSW

### Purpose

Integration tests validate that **actual request payloads** sent from frontend to backend have the correct structure. This is different from contract tests which only validate schema compatibility.

### MSW Setup

```typescript
// vitest.setup.ts
import { server } from '@/auth/test-utils/mock-server'

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
```

### Integration Test Pattern

```typescript
// frontend/src/__tests__/integration/user-requests.test.ts
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/auth/test-utils/mock-server'
import { deleteUser } from '@/users/api'

describe('User Request Integration Tests', () => {
  it('DELETE /users/{user_id} sends string ID in path parameter', async () => {
    let capturedUserId: string | undefined

    server.use(
      http.delete('http://localhost:26154/users/:user_id', ({ params }) => {
        capturedUserId = params.user_id as string
        return HttpResponse.json({ message: 'User deleted successfully' })
      }),
    )

    await deleteUser('usr_2k4h6j8m9n0p1q2r')

    expect(capturedUserId).toBeDefined()
    expect(typeof capturedUserId).toBe('string')
    expect(capturedUserId).toBe('usr_2k4h6j8m9n0p1q2r')
  })

  it('POST /users sends correct request body', async () => {
    let capturedBody: any

    server.use(
      http.post('http://localhost:26154/users', async ({ request }) => {
        capturedBody = await request.json()
        return HttpResponse.json({ id: 'usr_123', ...capturedBody })
      }),
    )

    await createUser({ email: 'test@example.com', name: 'Test User' })

    expect(capturedBody).toEqual({
      email: 'test@example.com',
      name: 'Test User'
    })
  })
})
```

### Contract vs Integration Tests

| Test Type | What It Validates | When It Fails |
|-----------|------------------|---------------|
| **Contract** | Schema compatibility | Backend changes response shape |
| **Integration** | Actual runtime behavior | `fetch()` sends wrong payload |

**Both are needed:**
- Contract tests catch schema mismatches at build time
- Integration tests catch runtime bugs in request construction

### Benefits of MSW

- Tests real `fetch()` calls (no mocking axios/fetch directly)
- Works with any HTTP library
- Can combine with openapi-backend for realistic mocks
- Tests fail if response shape doesn't match frontend schemas

---

## Shared Test Fixtures

Keep test data close to the behavior it supports. A fixture used by one test or
one tightly related test module can remain beside that test. Move reusable
builders, representative payloads, and feature-level integration helpers into
the owning feature's `testing/` directory when sharing them improves clarity or
keeps an important domain example consistent.

The `testing/` directory is an ownership boundary, not a mandatory file
template. Use names that describe the artifact, such as `fixtures.ts`,
`make-trace-evidence.ts`, or a named integration payload. Do not introduce a
global fixture directory merely to remove duplication between unrelated
features. Cross-feature fixtures should remain owned by the feature or contract
that defines the data and be imported from there.

Shared fixtures should:

- be deterministic and contain only the fields relevant to the behavior under
  test
- use the production types or schemas they represent
- expose builders when individual tests need explicit variations
- preserve meaningful integration payloads as checked-in data when readability
  is better than constructing them inline
- change with the owning contract rather than masking schema drift with broad
  type assertions

Current examples include `features/agent-executions/testing/fixtures.ts`,
`features/evaluation-runs/testing/fixtures.ts`, and
`features/traces/testing/make-trace-evidence.ts`.

---

## Common Testing Pitfalls

### Pitfall 1: Type Assertions in Tests

❌ **Don't do this:**
```typescript
const result = await getUser('123')
const user = result as UserRead  // Bypasses TypeScript checking
```

✅ **Do this:**
```typescript
const result = await getUser('123')
const user = UserReadSchema.parse(result)  // Validates at runtime
```

**Why:** Type assertions hide bugs. Runtime validation catches them.

### Pitfall 2: Excluding Test Files from TypeScript

❌ **Don't do this:**
```json
// tsconfig.app.json
{
  "exclude": ["**/*.test.ts", "**/*.test.tsx"]
}
```

✅ **Do this:**
```json
// tsconfig.app.json
{
  "include": ["src"]  // Includes tests
}
```

**Why:** TypeScript catches errors in tests too. Don't disable it.

### Pitfall 3: Not Validating Path Parameter Types

❌ **Don't assume parameters are correct type:**
```typescript
// No validation of parameter type
it('deletes user', async () => {
  await deleteUser('123')
  // How do we know backend expects string vs number?
})
```

✅ **Validate both contract AND runtime behavior:**
```typescript
// Contract test
it('user_id parameter is string type', () => {
  const param = api.getOperation('delete_user')?.parameters?.[0]
  expect(param?.schema?.type).toBe('string')
})

// Integration test
it('sends string ID in request', async () => {
  server.use(http.delete('/users/:id', ({ params }) => {
    expect(typeof params.id).toBe('string')
    return HttpResponse.json({ success: true })
  }))
  await deleteUser('usr_123')
})
```

### Pitfall 4: Duplicate Type Definitions

❌ **Don't do this:**
```typescript
// Duplicated definitions
interface UserRead {
  id: string
  email: string
}

const UserReadSchema = z.object({
  id: z.string(),
  email: z.string(),
})
```

✅ **Do this:**
```typescript
// Single source of truth
const UserReadSchema = z.object({
  id: z.string(),
  email: z.string(),
})

type UserRead = z.infer<typeof UserReadSchema>
```

### Pitfall 5: Not Testing Request Payloads

❌ **Don't only test that request succeeds:**
```typescript
it('creates user', async () => {
  const user = await createUser({ email: 'test@example.com' })
  expect(user.id).toBeDefined()
  // But did we send the right payload?
})
```

✅ **Capture and validate actual payload:**
```typescript
it('creates user with correct payload', async () => {
  let capturedBody: any
  server.use(http.post('/users', async ({ request }) => {
    capturedBody = await request.json()
    return HttpResponse.json({ id: '123', ...capturedBody })
  }))

  await createUser({ email: 'test@example.com' })
  expect(capturedBody).toEqual({ email: 'test@example.com' })
})
```

### Pitfall 6: Not Testing Edge Cases

❌ **Don't only test happy path:**
```typescript
it('creates user', async () => {
  const user = await createUser({ email: 'test@example.com' })
  expect(user).toBeDefined()
})
```

✅ **Test special characters, long values, error responses:**
```typescript
it('creates user with special characters in email', async () => {
  const user = await createUser({ email: 'test+tag@example.com' })
  expect(user.email).toBe('test+tag@example.com')
})

it('handles long email addresses', async () => {
  const longEmail = 'a'.repeat(50) + '@example.com'
  const user = await createUser({ email: longEmail })
  expect(user.email).toBe(longEmail)
})

it('handles server errors gracefully', async () => {
  server.use(http.post('/users', () => HttpResponse.json(
    { error: 'Email already exists' },
    { status: 400 }
  )))

  await expect(createUser({ email: 'existing@example.com' }))
    .rejects.toThrow('Email already exists')
})
```

---

## Backend Test Markers

### All Available Markers

```python
@pytest.mark.unit              # Fast, isolated unit tests
@pytest.mark.integration        # Integration tests that use real database
@pytest.mark.requires_grpc_server  # Tests requiring gRPC server (handled by fixture)
@pytest.mark.security          # Security tests (auth bypass, SQL injection)
@pytest.mark.concurrency       # Concurrency and race condition tests
@pytest.mark.error_recovery    # Error recovery and resilience tests
@pytest.mark.requires_gemini_api   # Tests requiring GEMINI_API_KEY
@pytest.mark.requires_openai_api   # Tests requiring OPENAI_API_KEY
@pytest.mark.requires_anthropic_api # Tests requiring ANTHROPIC_API_KEY
```

### Usage Examples

```python
@pytest.mark.unit
def test_hash_password():
    """Unit test - no external dependencies"""
    hashed = hash_password("password123")
    assert verify_password("password123", hashed)

@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_user():
    """Integration test - uses real database via autouse fixture"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/users", json={"email": "test@example.com"})
        assert response.status_code == 200

@pytest.mark.security
@pytest.mark.asyncio
async def test_sql_injection_prevention():
    """Security test - validates input sanitization"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/users?email='; DROP TABLE users; --")
        assert response.status_code in [400, 404]  # Not 500

@pytest.mark.requires_openai_api
@pytest.mark.asyncio
async def test_openai_generation():
    """Test requiring actual OpenAI API key"""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    response = await generate_completion(model="gpt-4o", prompt="Hello")
    assert response.content
```

### gRPC Integration Tests

**How they work:**
These tests use a special fixture `grpc_server_for_tests` (in `backend/app/features/internal_auth/conftest.py`) that:
1. Creates an isolated temporary SQLite database
2. Starts the gRPC server in a background thread within the test process
3. Configures the server to use the isolated database

**Why this is better than starting `uvicorn`:**
- **Isolation:** Each test run gets a fresh database
- **Consistency:** Tests can seed data (like API keys) into the isolated DB and immediately use them
- **Control:** Tests can manage the server lifecycle directly

**Important:** Do NOT run `uvicorn` (or `docker compose up`) before running these tests. If port 50053 is in use, the tests will fail because they can't bind to the port (or will connect to the wrong server).

### Running Specific Test Categories

```bash
# Run only unit tests (fast)
pytest -m unit

# Run integration tests
pytest -m integration

# Run everything except tests requiring API keys
pytest -m "not (requires_openai_api or requires_gemini_api or requires_anthropic_api)"

# Run security and error recovery tests
pytest -m "security or error_recovery"
```

---

## Summary

**Testing philosophy:**
- Contract tests ensure schema compatibility
- Integration tests validate runtime behavior
- Both are needed for full coverage
- Keep fixtures local until feature-level sharing improves clarity or consistency
- Validate at runtime, don't use type assertions
- Test edge cases, not just happy paths

**Key files:**
- `frontend/src/__tests__/contracts/` - Contract tests
- `frontend/src/__tests__/integration/` - Integration tests
- `frontend/src/features/{feature}/testing/` - Feature-owned fixtures and test helpers
- Backend: Co-located `test_*.py` files with markers
