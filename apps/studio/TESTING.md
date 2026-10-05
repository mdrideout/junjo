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
10. [Backend Test Layers](#backend-test-layers)
11. [Real-World Runs](#real-world-runs)

---

## Running Tests

### Backend Tests (All Tests)

Run the complete backend test collection for both crates, including the
cross-service tests that start the real ingestion service:

```bash
cd backend
cargo test --locked
```

**What it does:**
- Runs every test in the `evidence` and `server` crates
- Builds the ingestion release binary for the cross-service tests, which takes minutes on a clean checkout
- Gives each test its own temporary databases and ephemeral ports

**What it needs:**
- `protoc` 30.2 on your `PATH` (see `PROTO_VERSIONS.md`)
- Nothing from a running Studio stack: no test binds a fixed port or opens `.dbdata`

See [Backend Test Layers](#backend-test-layers) for what each layer proves.

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

**Backend - Evidence crate only (no `protoc`, no DataFusion build, no ingestion build):**
```bash
cd backend
cargo test --locked -p junjo-evidence
```

---

## Local Agent E2E Identity

The local default user is created through Studio's public first-user setup API,
the same contract used by the setup form. It is not a database seed and is
never created by startup, Compose, the schema, or a build:

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

This is also the reset to use when the backend refuses to start because
`junjo.db` has another schema version. Studio has no upgrade path for
application data. For a deployed distribution, follow
[deployments/RESET.md](deployments/RESET.md) instead.

The validator asks Studio whether setup is required and, only on an empty
deployment, submits `admin@test.com` through
`/api/v1/users/create-first-user`. It uses a separate random user and
credentials for the proof, removes those disposable records through the HTTP
API, and finishes by signing the retained owner out and back in. Existing-user
distribution tests supply paired credentials through
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

**The backend's Rust request and response types are the single source of truth.**

Frontend Zod schemas are validated against backend OpenAPI schemas to ensure compatibility. This catches breaking changes before they reach production.

### How It Works

1. **Backend types carry examples** in their schema attributes. `backend/server/src/features/auth/users.rs` shows the pattern. The OpenAPI document is generated from those types and the registered routes.

2. **Export the OpenAPI document** to `frontend/backend/openapi.json` and run the contract tests against it:
   ```bash
   ./backend/scripts/validate_rest_api_contracts.sh
   ```
   The document is a committed file. A change in it is a contract change and is reviewed as one.

3. **Frontend contract tests** validate Zod schemas can parse OpenAPI-generated mocks:
   ```typescript
   import { generateMock } from '../../auth/test-utils/openapi-mock-generator'
   import { ListUsersResponseSchema } from '../../features/users/schema'

   describe('API Contract: UserRead Schema', () => {
     it('Zod schema can parse OpenAPI-generated mock', () => {
       const { mock } = generateMock('list_users')
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
describe('API Contract: DELETE /api/v1/users/{user_id}', () => {
  it('user_id parameter is defined as string', () => {
    const operation = api.getOperation('delete_user')
    const userIdParam = operation?.parameters?.find((p) => p.name === 'user_id')

    expect(userIdParam).toBeDefined()
    expect(userIdParam?.schema?.type).toBe('string')
  })
})
```

**Why this matters:** Common bug is treating string IDs as numbers. This test ensures backend schema matches frontend expectations.

### Contract Test Example (Complete)

```typescript
// frontend/src/__tests__/contracts/read-contracts.test.ts
import { describe, expect, it } from 'vitest'
import { generateMock } from '../../auth/test-utils/openapi-mock-generator'
import { ListUsersResponseSchema } from '../../features/users/schema'
import { ListApiKeysResponseSchema } from '../../features/api-keys/schemas'

describe('API Contract: Frontend Zod Schemas Match Backend OpenAPI', () => {
  it('Zod schema can parse OpenAPI-generated user list mock', () => {
    const { mock } = generateMock('list_users')
    const result = ListUsersResponseSchema.parse(mock)
    expect(Array.isArray(result)).toBe(true)
  })

  it('Zod schema can parse OpenAPI-generated API key list mock', () => {
    const { mock } = generateMock('list_api_keys')
    const result = ListApiKeysResponseSchema.parse(mock)
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
// frontend/src/auth/test-utils/test-setup.ts
import { server } from './mock-server'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
```

A request with no handler fails its test. The app calls the API with relative
URLs, so handlers use `API_BASE` from `mock-server.ts`, the origin of the test
page.

### Integration Test Pattern

```typescript
// frontend/src/__tests__/integration/mutation-requests.test.ts
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { API_BASE, server } from '../../auth/test-utils/mock-server'
import { deleteUser } from '../../features/users/fetch/delete-user'

describe('API Request Validation: Mutation Operations', () => {
  it('DELETE /api/v1/users/{user_id} sends string ID in path parameter', async () => {
    let capturedUserId: string | undefined

    server.use(
      http.delete(`${API_BASE}/api/v1/users/:user_id`, ({ params }) => {
        capturedUserId = params.user_id as string
        return HttpResponse.json({ message: 'User deleted successfully' })
      }),
    )

    await deleteUser('usr_2k4h6j8m9n0p1q2r')

    expect(capturedUserId).toBeDefined()
    expect(typeof capturedUserId).toBe('string')
    expect(capturedUserId).toBe('usr_2k4h6j8m9n0p1q2r')
  })
})
```

The same file captures and checks request bodies for the routes that take one.

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
  server.use(http.delete(`${API_BASE}/api/v1/users/:id`, ({ params }) => {
    expect(typeof params.id).toBe('string')
    return HttpResponse.json({ message: 'User deleted successfully' })
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
  server.use(http.post(`${API_BASE}/api/v1/users`, async ({ request }) => {
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
  server.use(http.post(`${API_BASE}/api/v1/users`, () => HttpResponse.json(
    { code: 'user_email_exists', message: 'A user with this email already exists' },
    { status: 409 }
  )))

  await expect(createUser({ email: 'existing@example.com' }))
    .rejects.toThrow('A user with this email already exists')
})
```

---

## Backend Test Layers

Backend tests are Rust tests beside the code they cover. A feature's tests are
in its module or in a `tests.rs` beside it. `cargo test --locked` from
`backend/` runs every layer.

| Layer | Where | What it proves |
| --- | --- | --- |
| Router tests | `backend/server/src/app.rs` and the feature tests under `backend/server/src/features/` | Requests through the real router and its layers, against a complete application over temporary databases |
| Schema and statement tests | `backend/server/src/db/` | Each schema file creates an empty database, and every SQL statement a feature lists prepares against it |
| Query and indexer tests | `backend/server/src/features/otel_spans/` and `backend/server/src/features/parquet_indexer/` | Queries and the metadata indexer over Parquet files that the tests write with ingestion's schema |
| Internal gRPC tests | `backend/server/src/features/internal_auth.rs` | `ValidateApiKey`, including over a real transport on an ephemeral port |
| Process tests | `backend/server/src/main.rs` | Startup, both listeners, UI serving, and shutdown |
| Evidence tests | `backend/evidence/` | Evidence logic against the shared fixtures in `contracts/telemetry/fixtures` |
| Cross-service tests | `backend/server/src/cross_service_tests/` | The backend against the real ingestion service |

### Router Tests

`backend/server/src/test_support.rs` builds the application and
`backend/server/src/test_http.rs` sends requests through its router, in
process and without a listener. Every test gets its own databases, so tests
share no state. Ingestion is a stand-in that answers what the test tells it.
Only the cross-service tests use the real service.

### Every Route Requires a Credential

One test in `backend/server/src/app.rs` walks every operation in the exported
OpenAPI document and sends it a request that carries no credential. Each route
must refuse it with 401 and the standard error body, except the public routes
that test lists.

A new route is covered without a new test. Making a route public means adding
it to that list on purpose.

### Evidence Tests and Generated Projections

The `evidence` crate performs no I/O. Its tests need no database, no `protoc`,
and no ingestion binary.

Committed files hold what the assemblers produce from the valid fixtures:

- the files under `backend/evidence/tests/generated/`
- `frontend/src/features/workflow-executions/testing/workflow-store-projections.json`

Frontend tests read them, so the frontend is tested against real backend
output without running a backend. The `generated_projections` test fails when
a file is not, text for text, what the assemblers produce now. The header of
`backend/evidence/tests/generated_projections.rs` lists every file and the
command that regenerates them. After a deliberate change, run it and review
the difference as a contract change.

### Cross-Service Tests

Each test starts its own ingestion process with its own ports and temporary
directory, sends spans to it over OTLP, and asserts through the backend's
ingestion client, span repository, or HTTP routes. They cover the WAL flush,
the hot snapshot, a query racing a flush, concurrent queries while ingestion
replaces the snapshot, the recent-cold bridge, the LLM filter, and the shared
transport fixtures at each storage stage.

The first of these tests to run builds the ingestion release binary with
`cargo build --release --locked` in `ingestion/`. On a clean checkout that
takes minutes. A failed test prints its ingestion process's log.

---

## Real-World Runs

The tests above prove behavior. They do not show what Studio's pages do while
spans arrive, on the resource profile Studio supports.

A change to the query path, the backend, or ingestion is therefore also run
with the real frontend in a browser and the real SDK while a load generator
sends spans to ingestion, and compared with the unchanged build.
[`ingestion/benchmarks/README.md`](ingestion/benchmarks/README.md) owns the
procedure under "Real-world runs". It starts its own disposable stack and
never uses a running one.

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
- `backend/server/src/` - Backend tests, beside the code they cover
- `backend/evidence/tests/` - Evidence fixture tests and the generated projection check
