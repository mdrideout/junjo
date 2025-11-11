/**
 * Unit tests for navigation-helpers.ts
 *
 * Tests the getPostSignInDestination() function which determines
 * where to navigate users after sign-in based on their API key status.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from './test-utils/mock-server'
import { getPostSignInDestination } from './navigation-helpers'

describe('getPostSignInDestination', () => {
  beforeEach(() => {
    // Clear console to avoid noise from expected error logs
    vi.spyOn(console, 'log').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('should return /api-keys when user has no API keys', async () => {
    // Default mock handler returns empty array []
    const destination = await getPostSignInDestination()

    expect(destination).toBe('/api-keys')
  })

  it('should return / (home) when user has API keys', async () => {
    // Override the default handler to return a list with one API key
    server.use(
      http.get('http://localhost:1323/api_keys', () => {
        return HttpResponse.json([
          {
            id: 'test-key-id',
            key: 'test-key-value',
            name: 'Test Key',
            created_at: '2025-01-01T00:00:00',
          },
        ])
      })
    )

    const destination = await getPostSignInDestination()

    expect(destination).toBe('/')
  })

  it('should return / (home) when API fetch fails', async () => {
    // Override the default handler to return an error
    server.use(
      http.get('http://localhost:1323/api_keys', () => {
        return HttpResponse.json(
          { detail: 'Unauthorized' },
          { status: 401 }
        )
      })
    )

    const destination = await getPostSignInDestination()

    expect(destination).toBe('/')
  })

  it('should return / (home) when network error occurs', async () => {
    // Override the default handler to simulate network error
    server.use(
      http.get('http://localhost:1323/api_keys', () => {
        return HttpResponse.error()
      })
    )

    const destination = await getPostSignInDestination()

    expect(destination).toBe('/')
  })
})
