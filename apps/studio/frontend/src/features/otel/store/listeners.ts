import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import { AppDispatch, RootState } from '../../../root-store/store'
import { OtelStateActions } from './slice'
import { fetchOtelSpans } from '../fetch'

export const otelStateListenerMiddleware = createListenerMiddleware()
const startListener = otelStateListenerMiddleware.startListening.withTypes<RootState, AppDispatch>()

startListener({
  actionCreator: OtelStateActions.fetchData,
  effect: async (_action, listenerApi) => {
    // Clear errors and set loading
    listenerApi.dispatch(OtelStateActions.setError(false))
    listenerApi.dispatch(OtelStateActions.setLoading(true))

    // Fetch the data
    try {
      const response = await fetchOtelSpans()
      listenerApi.dispatch(OtelStateActions.setData(response))
    } catch (error) {
      listenerApi.dispatch(OtelStateActions.setError(true))
    } finally {
      listenerApi.dispatch(OtelStateActions.setLoading(false))
    }
  },
})
