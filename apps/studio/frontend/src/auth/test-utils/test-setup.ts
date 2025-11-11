/**
 * Vitest setup file for auth integration tests.
 *
 * This file is loaded before each test file and:
 * - Imports jest-dom matchers for better assertions
 * - Initializes MSW (Mock Service Worker) for API mocking
 * - Cleans up after each test
 */

import '@testing-library/jest-dom'
import { beforeAll, afterEach, afterAll } from 'vitest'
import { server } from './mock-server'

// Start MSW server before all tests
beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
})

// Reset handlers after each test to ensure test isolation
afterEach(() => {
  server.resetHandlers()
})

// Clean up after all tests
afterAll(() => {
  server.close()
})
