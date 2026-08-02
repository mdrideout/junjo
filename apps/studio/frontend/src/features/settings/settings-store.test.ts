import { waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { API_BASE, server } from '../../auth/test-utils/mock-server'
import { createAppStore } from '../../root-store/store'
import { SettingsStateActions, settingsReducer } from './slice'

describe('settings state', () => {
  it('uses the supplied completion timestamp in a coherent successful transition', () => {
    const state = settingsReducer(
      settingsReducer(undefined, SettingsStateActions.flushWalStarted()),
      SettingsStateActions.flushWalSucceeded({ completedAt: 789 }),
    )

    expect(state).toEqual({
      flushWalLoading: false,
      flushWalError: null,
      flushWalSuccess: true,
      lastFlushTime: 789,
    })
  })

  it('stores an unsuccessful flush response as one failed transition', async () => {
    server.use(
      http.post(`${API_BASE}/api/admin/flush-wal`, () =>
        HttpResponse.json({ success: false, message: 'Nothing flushed' }),
      ),
    )
    const store = createAppStore()

    store.dispatch(SettingsStateActions.flushWal())

    await waitFor(() => {
      expect(store.getState().settingsState).toEqual({
        flushWalLoading: false,
        flushWalError: 'Nothing flushed',
        flushWalSuccess: false,
        lastFlushTime: null,
      })
    })
  })
})
