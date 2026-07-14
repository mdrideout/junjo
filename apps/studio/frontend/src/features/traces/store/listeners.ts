import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import { AppDispatch, RootState } from '../../../root-store/store'
import { TracesStateActions } from './slice'
import { getTraceEvidence } from '../fetch/get-trace-evidence'
import { fetchServiceNames } from '../fetch/get-service-names'

export const otelStateListenerMiddleware = createListenerMiddleware()
const startListener = otelStateListenerMiddleware.startListening.withTypes<RootState, AppDispatch>()

startListener({
  actionCreator: TracesStateActions.fetchServiceNames,
  effect: async (_action, listenerApi) => {
    const loading = listenerApi.getState().tracesState.serviceNames.loading
    if (loading) return

    // Clear errors and set loading
    listenerApi.dispatch(TracesStateActions.setServiceNamesError(false))
    listenerApi.dispatch(TracesStateActions.setServiceNamesLoading(true))

    // Fetch the data
    try {
      const data = await fetchServiceNames()
      listenerApi.dispatch(TracesStateActions.setServiceNamesData(data))
    } catch {
      listenerApi.dispatch(TracesStateActions.setServiceNamesError(true))
    } finally {
      listenerApi.dispatch(TracesStateActions.setServiceNamesLoading(false))
    }
  },
})

startListener({
  actionCreator: TracesStateActions.fetchTraceEvidence,
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
      const data = await getTraceEvidence(traceId)
      dispatch(
        TracesStateActions.setTraceEvidenceData({
          traceId,
          data,
        }),
      )
    } catch {
      dispatch(TracesStateActions.setTracesError(true))
    } finally {
      dispatch(TracesStateActions.setTracesLoading(false))
    }
  },
})
