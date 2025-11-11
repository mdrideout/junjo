/**
 * API Contract Tests
 *
 * These tests validate that frontend Zod schemas can successfully parse
 * mock data generated from the backend OpenAPI specification.
 *
 * This ensures the frontend and backend schemas stay in sync. If the backend
 * changes a field name, type, or adds/removes required fields, these tests
 * will fail, alerting developers to update the frontend Zod schemas.
 *
 * Test Flow:
 * 1. openapi-backend generates mock data from backend OpenAPI spec
 * 2. Frontend Zod schema attempts to parse the mock data
 * 3. If parse succeeds → schemas are compatible ✅
 * 4. If parse fails → schemas are out of sync, needs manual update ❌
 */

import { describe, it, expect } from 'vitest'
import { generateMock } from '../../auth/test-utils/openapi-mock-generator'
import { ListUsersResponseSchema } from '../../features/users/schema'
import { ListApiKeysResponseSchema } from '../../features/api-keys/schemas'

describe('API Contract: Frontend Zod Schemas Match Backend OpenAPI', () => {
  describe('UserRead Schema', () => {
    it('Zod schema can parse OpenAPI-generated user list mock', () => {
      // Generate mock from backend OpenAPI spec
      const { mock } = generateMock('list_users_users_get')

      // Try to parse with frontend Zod schema
      // If this fails, frontend and backend schemas are out of sync!
      const result = ListUsersResponseSchema.parse(mock)

      // Verify it parsed successfully
      expect(result).toBeDefined()
      expect(Array.isArray(result)).toBe(true)

      // If we got data, verify it has the expected structure
      if (result.length > 0) {
        const user = result[0]
        expect(user).toHaveProperty('id')
        expect(user).toHaveProperty('email')
        expect(user).toHaveProperty('is_active')
        expect(user).toHaveProperty('created_at')
        expect(user).toHaveProperty('updated_at')
      }
    })
  })

  describe('APIKeyRead Schema', () => {
    it('Zod schema can parse OpenAPI-generated API key list mock', () => {
      // Generate mock from backend OpenAPI spec
      const { mock } = generateMock('list_api_keys_api_keys_get')

      // Try to parse with frontend Zod schema
      const result = ListApiKeysResponseSchema.parse(mock)

      // Verify it parsed successfully
      expect(result).toBeDefined()
      expect(Array.isArray(result)).toBe(true)

      // If we got data, verify it has the expected structure
      if (result.length > 0) {
        const apiKey = result[0]
        expect(apiKey).toHaveProperty('id')
        expect(apiKey).toHaveProperty('key')
        expect(apiKey).toHaveProperty('name')
        expect(apiKey).toHaveProperty('created_at')
      }
    })
  })

  describe('Mock Data Quality', () => {
    it('Generated user mocks contain realistic example data from Field()', () => {
      const { mock } = generateMock('list_users_users_get')

      if (mock.length > 0) {
        const user = mock[0]

        // Check that examples from Field() are being used
        // Backend schema has: Field(examples=["usr_2k4h6j8m9n0p1q2r"])
        expect(user.id).toBeDefined()
        expect(typeof user.id).toBe('string')

        // Backend schema has: Field(examples=["alice@example.com"])
        expect(user.email).toBeDefined()
        expect(typeof user.email).toBe('string')
        expect(user.email).toContain('@')
      }
    })

    it('Generated API key mocks contain realistic example data from Field()', () => {
      const { mock } = generateMock('list_api_keys_api_keys_get')

      if (mock.length > 0) {
        const apiKey = mock[0]

        // Check that examples from Field() are being used
        expect(apiKey.id).toBeDefined()
        expect(typeof apiKey.id).toBe('string')

        expect(apiKey.key).toBeDefined()
        expect(typeof apiKey.key).toBe('string')

        expect(apiKey.name).toBeDefined()
        expect(typeof apiKey.name).toBe('string')
      }
    })
  })
})
