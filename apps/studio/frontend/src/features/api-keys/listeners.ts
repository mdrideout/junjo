import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import { ApiKeysStateActions } from './slice'
import { AppDispatch, RootState } from '../../root-store/store'
import { fetchApiKeys } from './fetch/list-api-keys'
import { deleteApiKey } from './fetch/delete-api-key'

export const apiKeysStateListenerMiddleware = createListenerMiddleware()
const startListener = apiKeysStateListenerMiddleware.startListening.withTypes<RootState, AppDispatch>()

// LIST
startListener({
  actionCreator: ApiKeysStateActions.fetchApiKeysData,
  effect: async (action, { getState, dispatch }) => {
    const { force } = action.payload
    const { loading, lastUpdated } = getState().apiKeysState
    const fresh = lastUpdated !== null && Date.now() - lastUpdated < 2_000
    if (!force && (loading || fresh)) return

    dispatch(ApiKeysStateActions.loadStarted())
    try {
      const apiKeys = await fetchApiKeys()
      dispatch(ApiKeysStateActions.loadSucceeded({ apiKeys, fetchedAt: Date.now() }))
    } catch {
      dispatch(ApiKeysStateActions.loadFailed('Failed to load application telemetry API keys.'))
    }
  },
})

// DELETE
startListener({
  actionCreator: ApiKeysStateActions.deleteApiKey,
  effect: async ({ payload }, { dispatch }) => {
    dispatch(ApiKeysStateActions.deleteStarted())
    try {
      await deleteApiKey(payload.id)
      dispatch(ApiKeysStateActions.deleteSucceeded())
      dispatch(ApiKeysStateActions.fetchApiKeysData({ force: true }))
    } catch {
      dispatch(ApiKeysStateActions.deleteFailed('Failed to delete application telemetry API key.'))
    }
  },
})
