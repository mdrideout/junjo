# Testing Guide

This document covers testing patterns and practices for Junjo AI Studio.

## Table of Contents

1. [Running Tests](#running-tests)
2. [Testing Strategy Overview](#testing-strategy-overview)
3. [Contract Testing (Frontend/Backend)](#contract-testing-frontendbackend)
4. [Integration Testing with MSW](#integration-testing-with-msw)
5. [Shared Test Fixtures](#shared-test-fixtures)
6. [Common Testing Pitfalls](#common-testing-pitfalls)
7. [Backend Test Markers](#backend-test-markers)

---

## Running Tests

### Backend Tests (All Tests)

Run all backend tests including gRPC integration tests:

```bash
cd backend
./scripts/run-backend-tests.sh
```

**What it does:**
- Runs unit tests (fast, no external dependencies)
- Runs integration tests (database tests without gRPC)
- Runs gRPC integration tests (starts in-process gRPC server with isolated DB)

**Why use this script:**
- Ensures all backend tests pass before committing
- Handles cleanup of temporary database files
- Validates that ports 1323 and 50053 are free before running gRPC tests

### Frontend Tests

Run all frontend tests:

```bash
cd frontend
npm test
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
      http.delete('http://localhost:1323/users/:user_id', ({ params }) => {
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
      http.post('http://localhost:1323/users', async ({ request }) => {
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

### The Problem

Duplicating mock data creators across multiple test files leads to:
- Inconsistent test data
- Maintenance burden (update in N places)
- ~150 lines of duplicated code

### The Solution: `__test__/fixtures.ts`

Extract shared mock data to centralized fixtures within each feature.

### File Structure

```
frontend/src/features/feature-name/
  utils/
    __test__/
      fixtures.ts              # Shared mock data creators
      test-utils.ts            # Test helper functions
    helper.test.ts             # Imports from __test__/fixtures.ts
  components/
    FeatureCard.test.tsx       # Imports from ../utils/__test__/fixtures.ts
```

### Example Fixtures File

```typescript
// frontend/src/features/spans/utils/__test__/fixtures.ts
import type { OtelSpan } from '@/spans/types'

export const createBaseSpan = (): OtelSpan => ({
  span_id: 'test-span-id',
  trace_id: 'test-trace-id',
  parent_span_id: null,
  name: 'test.span',
  start_time: new Date('2024-01-01T00:00:00Z'),
  end_time: new Date('2024-01-01T00:00:01Z'),
  status_code: 'OK',
  attributes_json: {},
  events_json: [],
})

export const createOpenAISpan = (): OtelSpan => ({
  ...createBaseSpan(),
  name: 'openai.chat.completion',
  attributes_json: {
    'llm.provider': 'openai',
    'llm.model_name': 'gpt-4o',
    'llm.invocation_parameters': '{"temperature": 0.7}',
    'input.value': 'Test prompt',
    'output.value': 'Test response',
  },
})

export const createSpanWithStructuredOutput = (): OtelSpan => ({
  ...createOpenAISpan(),
  attributes_json: {
    ...createOpenAISpan().attributes_json,
    'input.mime_type': 'application/json',
    'output.mime_type': 'application/json',
  },
})
```

### Usage in Tests

```typescript
// Component test
import { createOpenAISpan } from '../utils/__test__/fixtures'

describe('SpanCard', () => {
  it('renders LLM span data', () => {
    const span = createOpenAISpan()
    render(<SpanCard span={span} />)
    expect(screen.getByText('gpt-4o')).toBeInTheDocument()
  })
})

// Util test
import { createSpanWithStructuredOutput } from './__test__/fixtures'

describe('extractPromptData', () => {
  it('extracts structured output mime type', () => {
    const span = createSpanWithStructuredOutput()
    const result = extractPromptData(span)
    expect(result.hasStructuredOutput).toBe(true)
  })
})
```

### When to Extract Fixtures

**The Rule of Three:**
- Same mock data needed in 2+ test files → Extract to `fixtures.ts`
- Benefits appear immediately (consistency, maintainability)

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
- Extract shared fixtures to prevent duplication
- Validate at runtime, don't use type assertions
- Test edge cases, not just happy paths

**Key files:**
- `frontend/src/__tests__/contracts/` - Contract tests
- `frontend/src/__tests__/integration/` - Integration tests
- `frontend/src/features/{feature}/utils/__test__/fixtures.ts` - Shared fixtures
- Backend: Co-located `test_*.py` files with markers
