import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import { AppDispatch, RootState } from '../../../root-store/store'
import { TracesStateActions } from './slice'
import { getTraceSpans } from '../fetch/get-trace-spans'
import { fetchServiceNames } from '../fetch/get-service-names'

export const otelStateListenerMiddleware = createListenerMiddleware()
const startListener = otelStateListenerMiddleware.startListening.withTypes<RootState, AppDispatch>()

startListener({
  actionCreator: TracesStateActions.fetchServiceNames,
  effect: async (_action, listenerApi) => {
    // Clear errors and set loading
    listenerApi.dispatch(TracesStateActions.setServiceNamesError(false))
    listenerApi.dispatch(TracesStateActions.setServiceNamesLoading(true))

    // Fetch the data
    try {
      const data = await fetchServiceNames()
      listenerApi.dispatch(TracesStateActions.setServiceNamesData(data))
    } catch (error) {
      listenerApi.dispatch(TracesStateActions.setServiceNamesError(true))
    } finally {
      listenerApi.dispatch(TracesStateActions.setServiceNamesLoading(false))
    }
  },
})

startListener({
  actionCreator: TracesStateActions.fetchSpansByTraceId,
  effect: async (action, { getState, dispatch }) => {
    const { traceId } = action.payload
    if (!traceId) throw new Error('No traceId provided')

    const loading = getState().tracesState.loading
    if (loading) return

    // // Cache busting logic
    // const now = Date.now()
    // const staleTime = 5 * 1000 // 5 seconds
    // const isStale = lastUpdated === null ? true : loading || now - lastUpdated < staleTime

    // // Bail out if already loading or not stale
    // if (loading || isStale === false) {
    //   console.log(`Bailing because loading is true (${loading}) or isStale is false (${isStale})`)
    //   return
    // }

    // Clear errors and set loading
    dispatch(TracesStateActions.setTracesError(false))
    dispatch(TracesStateActions.setTracesLoading(true))

    // Fetch the data
    try {
      const data = await getTraceSpans(traceId)
      dispatch(
        TracesStateActions.setTracesData({
          traceId,
          data,
        }),
      )
    } catch (error) {
      dispatch(TracesStateActions.setTracesError(true))
    } finally {
      dispatch(TracesStateActions.setTracesLoading(false))
    }
  },
})
