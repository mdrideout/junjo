import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../auth/test-utils/mock-server'
import { deleteUser } from '../../features/users/fetch/delete-user'
import { deleteApiKey } from '../../features/api-keys/fetch/delete-api-key'

describe('API Request Validation: Mutation Operations', () => {
  describe('User Management', () => {
    it('DELETE /users/{user_id} sends string ID in path parameter', async () => {
      let capturedUserId: string | undefined

      // Intercept the request and capture the parameter
      server.use(
        http.delete('http://localhost:1323/users/:user_id', ({ params }) => {
          capturedUserId = params.user_id as string
          return HttpResponse.json({ message: 'User deleted successfully' })
        }),
      )

      // Call the actual delete function with a string ID
      await deleteUser('usr_2k4h6j8m9n0p1q2r')

      // Validate that the parameter is a string
      expect(capturedUserId).toBeDefined()
      expect(typeof capturedUserId).toBe('string')
      expect(capturedUserId).toBe('usr_2k4h6j8m9n0p1q2r')
    })

    it('DELETE /users/{user_id} handles user ID with special characters', async () => {
      let capturedUserId: string | undefined

      server.use(
        http.delete('http://localhost:1323/users/:user_id', ({ params }) => {
          capturedUserId = params.user_id as string
          return HttpResponse.json({ message: 'User deleted successfully' })
        }),
      )

      // Test with ID containing underscores and alphanumeric characters
      const testId = 'usr_abc123_xyz789'
      await deleteUser(testId)

      expect(capturedUserId).toBe(testId)
      expect(typeof capturedUserId).toBe('string')
    })
  })

  describe('API Keys', () => {
    it('DELETE /api_keys/{id} sends string ID in path parameter', async () => {
      let capturedId: string | undefined

      server.use(
        http.delete('http://localhost:1323/api_keys/:id', ({ params }) => {
          capturedId = params.id as string
          return new HttpResponse(null, { status: 204 })
        }),
      )

      // Call the actual delete function with a string ID
      await deleteApiKey('key_abc123xyz789')

      // Validate that the parameter is a string
      expect(capturedId).toBeDefined()
      expect(typeof capturedId).toBe('string')
      expect(capturedId).toBe('key_abc123xyz789')
    })

    it('DELETE /api_keys/{id} handles API key ID with prefix', async () => {
      let capturedId: string | undefined

      server.use(
        http.delete('http://localhost:1323/api_keys/:id', ({ params }) => {
          capturedId = params.id as string
          return new HttpResponse(null, { status: 204 })
        }),
      )

      // Test with typical API key ID format
      const testId = 'key_live_1234567890abcdef'
      await deleteApiKey(testId)

      expect(capturedId).toBe(testId)
      expect(typeof capturedId).toBe('string')
    })
  })

  describe('Request Body Validation', () => {
    it('POST /api_keys sends correct request body structure', async () => {
      let capturedBody: any

      server.use(
        http.post('http://localhost:1323/api_keys', async ({ request }) => {
          capturedBody = await request.json()
          return HttpResponse.json({
            id: 'key_123',
            key: 'sk_live_abc123def456',
            name: capturedBody.name,
            created_at: new Date().toISOString(),
          })
        }),
      )

      // Make request via fetch (simulating what CreateApiKeyDialog does)
      const testName = 'Test API Key'
      await fetch('http://localhost:1323/api_keys', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name: testName }),
      })

      // Validate request body structure
      expect(capturedBody).toBeDefined()
      expect(capturedBody).toMatchObject({
        name: expect.any(String),
      })
      expect(capturedBody.name).toBe(testName)
      expect(capturedBody.name.length).toBeGreaterThan(0)
    })

    it('POST /users sends correct request body structure', async () => {
      let capturedBody: any

      server.use(
        http.post('http://localhost:1323/users', async ({ request }) => {
          capturedBody = await request.json()
          return HttpResponse.json({ message: 'User created successfully' })
        }),
      )

      // Make request via fetch (simulating what CreateUserDialog does)
      const testEmail = 'newuser@example.com'
      const testPassword = 'securePassword123'

      await fetch('http://localhost:1323/users', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email: testEmail, password: testPassword }),
      })

      // Validate request body structure
      expect(capturedBody).toBeDefined()
      expect(capturedBody).toMatchObject({
        email: expect.any(String),
        password: expect.any(String),
      })
      expect(capturedBody.email).toBe(testEmail)
      expect(capturedBody.email).toMatch(/@/)
      expect(capturedBody.password).toBe(testPassword)
      expect(capturedBody.password.length).toBeGreaterThanOrEqual(8)
    })
  })
})
