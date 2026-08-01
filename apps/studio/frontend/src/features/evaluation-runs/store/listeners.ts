import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import type { AppDispatch, RootState } from '../../../root-store/store'
import { listEvaluationDatasets } from '../fetch/list-evaluation-datasets'
import { getEvaluationDataset } from '../fetch/get-evaluation-dataset'
import { getEvaluationRun } from '../fetch/get-evaluation-run'
import { listEvaluationRuns } from '../fetch/list-evaluation-runs'
import { EvaluationIdSchema } from '../schemas/evaluation-runs'
import { getEvaluationRunListQueryKey } from '../schemas/query'
import { EvaluationRunsActions } from './slice'

export const evaluationRunsListenerMiddleware = createListenerMiddleware()
const startListener =
  evaluationRunsListenerMiddleware.startListening.withTypes<RootState, AppDispatch>()

startListener({
  actionCreator: EvaluationRunsActions.fetchEvaluationDataset,
  effect: async (action, { dispatch, getState }) => {
    const parsedDatasetId = EvaluationIdSchema.safeParse(action.payload)
    if (!parsedDatasetId.success) return
    const datasetId = parsedDatasetId.data
    if (getState().evaluationRunsState.datasetDetails[datasetId]?.loading) return

    dispatch(EvaluationRunsActions.setDatasetDetailError({ datasetId, error: null }))
    dispatch(EvaluationRunsActions.setDatasetDetailLoading({ datasetId, loading: true }))
    try {
      const data = await getEvaluationDataset(datasetId)
      dispatch(EvaluationRunsActions.setDatasetDetailData({ datasetId, data }))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch evaluation dataset'
      dispatch(EvaluationRunsActions.setDatasetDetailError({ datasetId, error: message }))
    } finally {
      dispatch(EvaluationRunsActions.setDatasetDetailLoading({ datasetId, loading: false }))
    }
  },
})

startListener({
  actionCreator: EvaluationRunsActions.fetchEvaluationDatasets,
  effect: async (_action, { dispatch, getState }) => {
    if (getState().evaluationRunsState.datasets.loading) return

    dispatch(EvaluationRunsActions.setDatasetsError(null))
    dispatch(EvaluationRunsActions.setDatasetsLoading(true))
    try {
      dispatch(EvaluationRunsActions.setDatasetsData(await listEvaluationDatasets()))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch evaluation datasets'
      dispatch(EvaluationRunsActions.setDatasetsError(message))
    } finally {
      dispatch(EvaluationRunsActions.setDatasetsLoading(false))
    }
  },
})

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
