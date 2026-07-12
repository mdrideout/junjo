# API Schema Validation

This directory contains scripts to prevent frontend/backend API contract drift using **industry-standard contract testing**.

## Philosophy

**Backend is the single source of truth.** Frontend Zod schemas are validated against backend OpenAPI schemas using:
- **MSW (Mock Service Worker)** - Intercepts HTTP requests in tests
- **openapi-backend** - Generates realistic mocks from OpenAPI specification
- **Existing Zod .parse()** - Validates that mocks match frontend schemas

## How It Works

### 1. Backend: Add Field() Examples to Pydantic Schemas

```python
class UserRead(BaseModel):
    id: str = Field(
        examples=["usr_2k4h6j8m9n0p1q2r"],
        description="Unique user identifier",
    )
    email: EmailStr = Field(
        examples=["alice@example.com"],
        description="User email address",
    )
```

These examples appear in the OpenAPI spec and are used to generate realistic test mocks.

### 2. Export OpenAPI Schema (`export_openapi_schema.py`)

- Imports FastAPI app directly (no server needed)
- Calls `app.openapi()` to generate schema
- Saves to `openapi.json` (gitignored)

### 3. Frontend: Contract Tests Validate Schemas

Tests use `openapi-backend` to generate mocks from OpenAPI spec, then validate with Zod:

```typescript
const { mock } = generateMock('list_users_users_get')
const result = ListUsersResponseSchema.parse(mock) // ✅ or ❌
```

**If backend changes a field:**
- openapi-backend generates mock with new field
- Frontend Zod schema can't parse it → **Test fails ❌**
- Developer updates frontend schema → Test passes ✅

### 4. CI/CD Integration (`validate_rest_api_contracts.sh`)

```bash
1. Export OpenAPI schema from backend
2. Copy to frontend
3. Run frontend contract tests
```

## Usage

### Local Validation

```bash
cd backend
./scripts/validate_rest_api_contracts.sh
```

Or run frontend tests directly:

```bash
cd frontend
npm run test:contracts
```

### CI/CD (GitHub Actions)

```yaml
- name: Validate API Schemas
  run: |
    cd backend
    ./scripts/validate_rest_api_contracts.sh
```

## What It Catches

✅ **Backend adds required field** → Zod parse fails (missing field)
✅ **Backend changes field type** → Zod parse fails (type mismatch)
✅ **Frontend has wrong field name** → Zod parse fails
✅ **Backend removes field** → Test passes (optional fields OK)
✅ **Field examples generate realistic data** → Tests use real-looking IDs, emails, etc.

## Adding New Schema Validations

### 1. Add Field() examples to backend Pydantic schema:

```python
class YourSchema(BaseModel):
    field: str = Field(
        examples=["example_value"],
        description="Field description",
    )
```

### 2. Create contract test:

```typescript
// frontend/src/__tests__/contracts/your-feature.test.ts
it('Zod schema can parse OpenAPI-generated mock', () => {
  const { mock } = generateMock('your_operation_id')
  const result = YourSchema.parse(mock)
  expect(result).toBeDefined()
})
```

### 3. Run tests:

```bash
npm run test:contracts
```

## Example: Schema Drift Detection

**Scenario: Backend adds `role` field to UserRead**

1. Backend adds `role: str = Field(examples=["admin"])`
2. Export OpenAPI → includes `role` field
3. openapi-backend generates mock: `{ ..., role: "admin" }`
4. MSW returns this mock in tests
5. Frontend `fetchUsers()` calls `ListUsersResponseSchema.parse(mock)`
6. **Zod parse FAILS** - `role` field not in schema ❌
7. Developer updates frontend Zod schema
8. Test passes ✅

## No Multiple Sources of Truth

This approach has **one source of truth**:
- **Backend Pydantic schemas** with Field(examples=[...])

Everything else is auto-generated:
- OpenAPI spec generated from Pydantic
- Mock data generated from OpenAPI
- Validation happens at runtime in tests

## Files

- `export_openapi_schema.py` - Generate OpenAPI from FastAPI
- `validate_rest_api_contracts.sh` - Run full validation pipeline
- `frontend/src/auth/test-utils/openapi-mock-generator.ts` - openapi-backend wrapper
- `frontend/src/__tests__/contracts/` - Contract validation tests
