import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import { AppDispatch, RootState } from '../../../root-store/store'
import { OtelStateActions } from './slice'
import { fetchOtelSpans } from '../fetch/fetch-otel-spans'
import { fetchServiceNames } from '../fetch/fetch-service-names'

export const otelStateListenerMiddleware = createListenerMiddleware()
const startListener = otelStateListenerMiddleware.startListening.withTypes<RootState, AppDispatch>()

startListener({
  actionCreator: OtelStateActions.fetchWorkflowsData,
  effect: async (action, { getState, dispatch }) => {
    const { serviceName } = action.payload
    if (!serviceName) throw new Error('No service name provided')

    const { loading, lastUpdated } = getState().otelState.workflows

    // Cache busting logic
    const now = Date.now()
    const staleTime = 5 * 1000 // 5 seconds
    const isStale = lastUpdated === null ? true : loading || now - lastUpdated < staleTime

    // Bail out if already loading or not stale
    if (loading || isStale === false) {
      console.log(`Bailing because loading is true (${loading}) or isStale is false (${isStale})`)
      return
    }

    // Clear errors and set loading
    dispatch(OtelStateActions.setWorkflowsError(false))
    dispatch(OtelStateActions.setWorkflowsLoading(true))

    // Fetch the data
    try {
      const data = await fetchOtelSpans(serviceName)
      console.log('Fetched data:', data)
      dispatch(OtelStateActions.setWorkflowsData({ serviceName, data }))
    } catch (error) {
      dispatch(OtelStateActions.setWorkflowsError(true))
    } finally {
      dispatch(OtelStateActions.setWorkflowsLoading(false))
    }
  },
})

startListener({
  actionCreator: OtelStateActions.fetchServiceNames,
  effect: async (_action, listenerApi) => {
    // Clear errors and set loading
    listenerApi.dispatch(OtelStateActions.setServiceNamesError(false))
    listenerApi.dispatch(OtelStateActions.setServiceNamesLoading(true))

    // Fetch the data
    try {
      const data = await fetchServiceNames()
      listenerApi.dispatch(OtelStateActions.setServiceNamesData(data))
    } catch (error) {
      listenerApi.dispatch(OtelStateActions.setServiceNamesError(true))
    } finally {
      listenerApi.dispatch(OtelStateActions.setServiceNamesLoading(false))
    }
  },
})
