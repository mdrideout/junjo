/**
 * MSW (Mock Service Worker) server configuration for auth integration tests.
 *
 * This file sets up request handlers to mock backend API responses during tests.
 * Individual tests can override these handlers using server.use() for specific scenarios.
 *
 * UPDATED: Now uses openapi-backend to generate mocks from OpenAPI spec,
 * ensuring mocks stay in sync with backend schemas automatically.
 */

import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'

// Base URL for API requests: the app calls the API with relative URLs, which
// resolve against the origin of the test page
export const API_BASE = window.location.origin

/**
 * Default request handlers for common API endpoints.
 * Tests can override these using server.use() for custom scenarios.
 */
export const handlers = [
  // Mock /api/v1/api-keys endpoint - auto-generated from OpenAPI spec
  // Returns empty array by default, but tests can override to return generated mocks
  http.get(`${API_BASE}/api/v1/api-keys`, () => {
    // Default: empty array (no API keys)
    // Tests can override with: generateMock('list_api_keys')
    return HttpResponse.json([])
  }),

  // Mock /api/v1/users/create-first-user endpoint - successful user creation
  http.post(`${API_BASE}/api/v1/users/create-first-user`, () => {
    return HttpResponse.json(
      { message: 'First user created successfully' },
      { status: 200 }
    )
  }),

  // Mock /api/v1/sign-in endpoint - successful sign-in
  http.post(`${API_BASE}/api/v1/sign-in`, () => {
    return HttpResponse.json({ message: 'signed in' }, { status: 200 })
  }),

  // Mock /api/v1/auth-test endpoint - user is authenticated
  http.get(`${API_BASE}/api/v1/auth-test`, () => {
    return HttpResponse.json({ user_email: 'test@example.com' }, { status: 200 })
  }),

  // Mock /api/v1/users/db-has-users endpoint - database has users after creation
  http.get(`${API_BASE}/api/v1/users/db-has-users`, () => {
    return HttpResponse.json({ users_exist: true }, { status: 200 })
  }),
]

/**
 * MSW server instance configured with default handlers.
 * Import this in test-setup.ts to start the server before tests.
 */
export const server = setupServer(...handlers)
