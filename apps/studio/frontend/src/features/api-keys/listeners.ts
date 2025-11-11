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
    const now = Date.now()
    const staleTime = 2000
    const isStale = lastUpdated === null ? true : loading || now - lastUpdated < staleTime

    if ((loading || !isStale) && !force) return

    dispatch(ApiKeysStateActions.setLoading(true))
    dispatch(ApiKeysStateActions.setError(false))
    try {
      const data = await fetchApiKeys()
      dispatch(ApiKeysStateActions.setApiKeys(data))
    } catch {
      dispatch(ApiKeysStateActions.setError(true))
    } finally {
      dispatch(ApiKeysStateActions.setLoading(false))
    }
  },
})

// DELETE
startListener({
  actionCreator: ApiKeysStateActions.deleteApiKey,
  effect: async ({ payload }, { dispatch }) => {
    dispatch(ApiKeysStateActions.setLoading(true))
    try {
      await deleteApiKey(payload.id)
    } catch {
      dispatch(ApiKeysStateActions.setError(true))
    } finally {
      dispatch(ApiKeysStateActions.setLoading(false))
      dispatch(ApiKeysStateActions.fetchApiKeysData({ force: true }))
    }
  },
})
