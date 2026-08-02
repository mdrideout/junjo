import { waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { API_BASE, server } from '../../auth/test-utils/mock-server'
import { createAppStore } from '../../root-store/store'
import type { User } from './schema'
import usersReducer, { UsersStateActions } from './slice'

const USER: User = {
  id: 'user-1',
  email: 'owner@example.com',
  is_active: true,
  created_at: '2026-08-01T15:00:00Z',
  updated_at: '2026-08-01T15:00:00Z',
}

describe('users state', () => {
  it('uses the supplied fetch timestamp in a coherent successful transition', () => {
    const state = usersReducer(
      usersReducer(undefined, UsersStateActions.loadStarted()),
      UsersStateActions.loadSucceeded({ users: [USER], fetchedAt: 123 }),
    )

    expect(state).toEqual({
      users: [USER],
      loading: false,
      error: null,
      lastUpdated: 123,
    })
  })

  it('keeps a fresh result, while stale and forced requests refresh it', async () => {
    let requestCount = 0
    server.use(
      http.get(`${API_BASE}/users`, () => {
        requestCount += 1
        return HttpResponse.json([USER])
      }),
    )
    const store = createAppStore()

    store.dispatch(UsersStateActions.loadSucceeded({ users: [USER], fetchedAt: Date.now() }))
    store.dispatch(UsersStateActions.fetchUsersData({ force: false }))
    expect(requestCount).toBe(0)

    store.dispatch(UsersStateActions.fetchUsersData({ force: true }))
    await waitFor(() => {
      expect(requestCount).toBe(1)
      expect(store.getState().usersState.loading).toBe(false)
    })

    store.dispatch(
      UsersStateActions.loadSucceeded({
        users: [USER],
        fetchedAt: Date.now() - 2_001,
      }),
    )
    store.dispatch(UsersStateActions.fetchUsersData({ force: false }))
    await waitFor(() => expect(requestCount).toBe(2))
  })

  it('keeps a deletion failure visible without refreshing the list', async () => {
    let listRequestCount = 0
    server.use(
      http.delete(`${API_BASE}/users/:userId`, () =>
        HttpResponse.json({ message: 'Delete failed' }, { status: 500 }),
      ),
      http.get(`${API_BASE}/users`, () => {
        listRequestCount += 1
        return HttpResponse.json([])
      }),
    )
    const store = createAppStore()
    store.dispatch(UsersStateActions.loadSucceeded({ users: [USER], fetchedAt: 123 }))

    store.dispatch(UsersStateActions.deleteUser({ id: USER.id }))

    await waitFor(() => {
      expect(store.getState().usersState).toMatchObject({
        users: [USER],
        loading: false,
        error: 'Failed to delete user.',
      })
    })
    expect(listRequestCount).toBe(0)
  })
})
