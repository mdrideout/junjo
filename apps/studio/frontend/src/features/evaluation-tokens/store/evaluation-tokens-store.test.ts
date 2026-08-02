import { waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { API_BASE, server } from '../../../auth/test-utils/mock-server'
import { createAppStore } from '../../../root-store/store'
import type { EvaluationTokenRead } from '../schemas'
import { EvaluationTokensActions, evaluationTokensReducer } from './slice'

const TOKEN: EvaluationTokenRead = {
  id: 'token-1',
  name: 'Coding agent',
  token: 'jcli_test-token',
  scopes: ['evaluation:read'],
  expires_at: null,
  created_by_user_id: 'user-1',
  created_at: '2026-08-01T15:00:00Z',
}

describe('evaluation token state', () => {
  it('uses the supplied timestamp and preserves cursor-based append behavior', () => {
    let state = evaluationTokensReducer(
      undefined,
      EvaluationTokensActions.loadSucceeded({
        items: [TOKEN],
        nextCursor: 'next-page',
        append: false,
        fetchedAt: 100,
      }),
    )
    state = evaluationTokensReducer(
      state,
      EvaluationTokensActions.loadSucceeded({
        items: [{ ...TOKEN, id: 'token-2' }, TOKEN],
        nextCursor: null,
        append: true,
        fetchedAt: 200,
      }),
    )

    expect(state.items.map((item) => item.id)).toEqual(['token-1', 'token-2'])
    expect(state).toMatchObject({
      loading: false,
      error: null,
      lastUpdated: 200,
      nextCursor: null,
    })
  })

  it('keeps a deletion failure visible without refreshing the list', async () => {
    let listRequestCount = 0
    server.use(
      http.delete(`${API_BASE}/api/v1/evaluation-tokens/:tokenId`, () =>
        HttpResponse.json({}, { status: 500 }),
      ),
      http.get(`${API_BASE}/api/v1/evaluation-tokens`, () => {
        listRequestCount += 1
        return HttpResponse.json({ items: [], next_cursor: null })
      }),
    )
    const store = createAppStore()
    store.dispatch(
      EvaluationTokensActions.loadSucceeded({
        items: [TOKEN],
        nextCursor: null,
        append: false,
        fetchedAt: 123,
      }),
    )

    store.dispatch(EvaluationTokensActions.deleteToken({ id: TOKEN.id }))

    await waitFor(() => {
      expect(store.getState().evaluationTokensState).toMatchObject({
        items: [TOKEN],
        loading: false,
        error: 'Failed to delete access token (500)',
      })
    })
    expect(listRequestCount).toBe(0)
  })
})
