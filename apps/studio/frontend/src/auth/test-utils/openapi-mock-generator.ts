/**
 * OpenAPI Mock Generator
 *
 * Uses openapi-backend to generate realistic mock responses from
 * the backend OpenAPI specification. This ensures MSW mocks stay
 * in sync with backend schema changes.
 *
 * The backend openapi.json is generated from FastAPI Pydantic schemas
 * which include Field(examples=[...]) for realistic test data.
 */

import OpenAPIBackend from 'openapi-backend'
import openapiSpec from '../../../backend/openapi.json'

// Initialize OpenAPI Backend with the specification
export const api = new OpenAPIBackend({
  definition: openapiSpec as any, // Type assertion: OpenAPI 3.1.0 not fully typed by openapi-backend
  strict: false, // Don't fail on unknown operations
  validate: false, // Disable OpenAPI spec validation (FastAPI uses 3.1.0 with JSON Schema 2020-12)
  quick: true, // Skip validation during init (FastAPI 3.1.0 not fully compatible with openapi-backend)
})

// Initialize the API (must be called before use)
// FastAPI generates OpenAPI 3.1.0 which uses JSON Schema 2020-12
// openapi-backend validates against OpenAPI 3.0.x, so we skip validation
try {
  api.init()
} catch (error) {
  // Ignore validation errors - FastAPI 3.1.0 compatibility issue
  console.warn('OpenAPI validation skipped (FastAPI 3.1.0 compatibility)')
}

/**
 * Generate a mock response for an OpenAPI operation.
 *
 * @param operationId - The operationId from the OpenAPI spec (e.g., 'listUsers')
 * @returns Object with status code and mock data
 *
 * @example
 * const { status, mock } = generateMock('listUsers')
 * // Returns: { status: 200, mock: [{ id: "usr_...", email: "alice@example.com", ... }] }
 */
export function generateMock(operationId: string): { status: number; mock: any } {
  const { status, mock } = api.mockResponseForOperation(operationId)
  return { status: status || 200, mock }
}
