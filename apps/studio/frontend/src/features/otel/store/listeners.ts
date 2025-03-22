import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import { AppDispatch, RootState } from '../../../root-store/store'
import { OtelStateActions } from './slice'
import { fetchOtelSpans } from '../fetch/fetch-otel-spans'
import { fetchServiceNames } from '../fetch/fetch-service-names'

export const otelStateListenerMiddleware = createListenerMiddleware()
const startListener = otelStateListenerMiddleware.startListening.withTypes<RootState, AppDispatch>()

startListener({
  actionCreator: OtelStateActions.fetchWorkflowsData,
  effect: async (action, listenerApi) => {
    const { serviceName } = action.payload

    // Clear errors and set loading
    listenerApi.dispatch(OtelStateActions.setWorkflowsError(false))
    listenerApi.dispatch(OtelStateActions.setWorkflowsLoading(true))

    if (!serviceName) {
      throw new Error('No service name provided')
    }

    // Fetch the data
    try {
      const data = await fetchOtelSpans(serviceName)
      listenerApi.dispatch(OtelStateActions.setWorkflowsData({ serviceName, data }))
    } catch (error) {
      listenerApi.dispatch(OtelStateActions.setWorkflowsError(true))
    } finally {
      listenerApi.dispatch(OtelStateActions.setWorkflowsLoading(false))
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
