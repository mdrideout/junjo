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
import { API_BASE, server } from './mock-server'

window.runtimeConfig = { API_HOST: API_BASE }

if (window.matchMedia === undefined) {
  window.matchMedia = (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  })
}

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
