import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import type { AppDispatch, RootState } from '../../../root-store/store'
import { getEvaluationRun } from '../fetch/get-evaluation-run'
import { listEvaluationRuns } from '../fetch/list-evaluation-runs'
import { EvaluationIdSchema } from '../schemas/evaluation-runs'
import { getEvaluationRunListQueryKey } from '../schemas/query'
import { EvaluationRunsActions } from './slice'

export const evaluationRunsListenerMiddleware = createListenerMiddleware()
const startListener =
  evaluationRunsListenerMiddleware.startListening.withTypes<RootState, AppDispatch>()

startListener({
  actionCreator: EvaluationRunsActions.fetchEvaluationRuns,
  effect: async (action, { dispatch, getState }) => {
    const key = getEvaluationRunListQueryKey(action.payload)
    if (getState().evaluationRunsState.lists[key]?.loading) return

    dispatch(EvaluationRunsActions.setListError({ key, error: null }))
    dispatch(EvaluationRunsActions.setListLoading({ key, loading: true }))
    try {
      const data = await listEvaluationRuns(action.payload)
      dispatch(EvaluationRunsActions.setListData({ key, data }))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch evaluation runs'
      dispatch(EvaluationRunsActions.setListError({ key, error: message }))
    } finally {
      dispatch(EvaluationRunsActions.setListLoading({ key, loading: false }))
    }
  },
})

startListener({
  actionCreator: EvaluationRunsActions.fetchEvaluationRun,
  effect: async (action, { dispatch, getState }) => {
    const parsedRunId = EvaluationIdSchema.safeParse(action.payload)
    if (!parsedRunId.success) return
    const runId = parsedRunId.data
    if (getState().evaluationRunsState.details[runId]?.loading) return

    dispatch(EvaluationRunsActions.setDetailError({ runId, error: null }))
    dispatch(EvaluationRunsActions.setDetailLoading({ runId, loading: true }))
    try {
      const data = await getEvaluationRun(runId)
      dispatch(EvaluationRunsActions.setDetailData({ runId, data }))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch evaluation run'
      dispatch(EvaluationRunsActions.setDetailError({ runId, error: message }))
    } finally {
      dispatch(EvaluationRunsActions.setDetailLoading({ runId, loading: false }))
    }
  },
})
