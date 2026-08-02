import { waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { API_BASE, server } from '../../auth/test-utils/mock-server'
import { createAppStore } from '../../root-store/store'
import type { ApiKey } from './schemas'
import { ApiKeysStateActions, apiKeysReducer } from './slice'

const API_KEY: ApiKey = {
  id: 'key-1',
  key: 'jtel_test-key',
  name: 'Test key',
  created_at: '2026-08-01T15:00:00Z',
}

describe('API key state', () => {
  it('uses the supplied fetch timestamp in a coherent successful transition', () => {
    const state = apiKeysReducer(
      apiKeysReducer(undefined, ApiKeysStateActions.loadStarted()),
      ApiKeysStateActions.loadSucceeded({ apiKeys: [API_KEY], fetchedAt: 456 }),
    )

    expect(state).toEqual({
      apiKeys: [API_KEY],
      loading: false,
      error: null,
      lastUpdated: 456,
    })
  })

  it('keeps a fresh result, while stale and forced requests refresh it', async () => {
    let requestCount = 0
    server.use(
      http.get(`${API_BASE}/api_keys`, () => {
        requestCount += 1
        return HttpResponse.json([API_KEY])
      }),
    )
    const store = createAppStore()

    store.dispatch(ApiKeysStateActions.loadSucceeded({ apiKeys: [API_KEY], fetchedAt: Date.now() }))
    store.dispatch(ApiKeysStateActions.fetchApiKeysData({ force: false }))
    expect(requestCount).toBe(0)

    store.dispatch(ApiKeysStateActions.fetchApiKeysData({ force: true }))
    await waitFor(() => {
      expect(requestCount).toBe(1)
      expect(store.getState().apiKeysState.loading).toBe(false)
    })

    store.dispatch(
      ApiKeysStateActions.loadSucceeded({
        apiKeys: [API_KEY],
        fetchedAt: Date.now() - 2_001,
      }),
    )
    store.dispatch(ApiKeysStateActions.fetchApiKeysData({ force: false }))
    await waitFor(() => expect(requestCount).toBe(2))
  })

  it('refreshes after a successful deletion', async () => {
    let listRequestCount = 0
    server.use(
      http.delete(`${API_BASE}/api_keys/:keyId`, () => new HttpResponse(null, { status: 204 })),
      http.get(`${API_BASE}/api_keys`, () => {
        listRequestCount += 1
        return HttpResponse.json([])
      }),
    )
    const store = createAppStore()
    store.dispatch(ApiKeysStateActions.loadSucceeded({ apiKeys: [API_KEY], fetchedAt: 123 }))

    store.dispatch(ApiKeysStateActions.deleteApiKey({ id: API_KEY.id }))

    await waitFor(() => {
      expect(listRequestCount).toBe(1)
      expect(store.getState().apiKeysState).toMatchObject({
        apiKeys: [],
        loading: false,
        error: null,
      })
    })
  })

  it('keeps a deletion failure visible without refreshing the list', async () => {
    let listRequestCount = 0
    server.use(
      http.delete(`${API_BASE}/api_keys/:keyId`, () => HttpResponse.json({}, { status: 500 })),
      http.get(`${API_BASE}/api_keys`, () => {
        listRequestCount += 1
        return HttpResponse.json([])
      }),
    )
    const store = createAppStore()
    store.dispatch(ApiKeysStateActions.loadSucceeded({ apiKeys: [API_KEY], fetchedAt: 123 }))

    store.dispatch(ApiKeysStateActions.deleteApiKey({ id: API_KEY.id }))

    await waitFor(() => {
      expect(store.getState().apiKeysState).toMatchObject({
        apiKeys: [API_KEY],
        loading: false,
        error: 'Failed to delete application telemetry API key.',
      })
    })
    expect(listRequestCount).toBe(0)
  })
})
