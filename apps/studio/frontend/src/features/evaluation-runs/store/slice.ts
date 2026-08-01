import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import type {
  EvaluationDatasetDetail,
  EvaluationDatasetListPage,
  EvaluationRunDetail,
  EvaluationRunListPage,
} from '../schemas/evaluation-runs'
import type { EvaluationRunListQuery } from '../schemas/query'

export interface EvaluationRequestState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

export interface EvaluationRunsState {
  datasets: EvaluationRequestState<EvaluationDatasetListPage>
  datasetDetails: Record<string, EvaluationRequestState<EvaluationDatasetDetail>>
  lists: Record<string, EvaluationRequestState<EvaluationRunListPage>>
  details: Record<string, EvaluationRequestState<EvaluationRunDetail>>
}

export const initialEvaluationRunsState: EvaluationRunsState = {
  datasets: { data: null, loading: false, error: null },
  datasetDetails: {},
  lists: {},
  details: {},
}

function requestState<T>(
  requests: Record<string, EvaluationRequestState<T>>,
  key: string,
): EvaluationRequestState<T> {
  requests[key] ??= { data: null, loading: false, error: null }
  return requests[key]
}

export const evaluationRunsSlice = createSlice({
  name: 'evaluationRunsState',
  initialState: initialEvaluationRunsState,
  reducers: {
    fetchEvaluationDatasets: () => {
      // Listener middleware owns the request.
    },
    fetchEvaluationRuns: {
      reducer: () => {
        // Listener middleware owns the request.
      },
      prepare: (query: EvaluationRunListQuery) => ({ payload: query }),
    },
    fetchEvaluationDataset: {
      reducer: () => {
        // Listener middleware owns the request.
      },
      prepare: (datasetId: string) => ({ payload: datasetId }),
    },
    fetchEvaluationRun: {
      reducer: () => {
        // Listener middleware owns the request.
      },
      prepare: (runId: string) => ({ payload: runId }),
    },
    setDatasetsLoading: (state, action: PayloadAction<boolean>) => {
      state.datasets.loading = action.payload
    },
    setDatasetsError: (state, action: PayloadAction<string | null>) => {
      state.datasets.error = action.payload
    },
    setDatasetsData: (
      state,
      action: PayloadAction<EvaluationDatasetListPage>,
    ) => {
      state.datasets.data = action.payload
    },
    setDatasetDetailLoading: (
      state,
      action: PayloadAction<{ datasetId: string; loading: boolean }>,
    ) => {
      requestState(state.datasetDetails, action.payload.datasetId).loading =
        action.payload.loading
    },
    setDatasetDetailError: (
      state,
      action: PayloadAction<{ datasetId: string; error: string | null }>,
    ) => {
      requestState(state.datasetDetails, action.payload.datasetId).error =
        action.payload.error
    },
    setDatasetDetailData: (
      state,
      action: PayloadAction<{ datasetId: string; data: EvaluationDatasetDetail }>,
    ) => {
      requestState(state.datasetDetails, action.payload.datasetId).data =
        action.payload.data
    },
    setListLoading: (
      state,
      action: PayloadAction<{ key: string; loading: boolean }>,
    ) => {
      requestState(state.lists, action.payload.key).loading = action.payload.loading
    },
    setListError: (
      state,
      action: PayloadAction<{ key: string; error: string | null }>,
    ) => {
      requestState(state.lists, action.payload.key).error = action.payload.error
    },
    setListData: (
      state,
      action: PayloadAction<{ key: string; data: EvaluationRunListPage }>,
    ) => {
      requestState(state.lists, action.payload.key).data = action.payload.data
    },
    setDetailLoading: (
      state,
      action: PayloadAction<{ runId: string; loading: boolean }>,
    ) => {
      requestState(state.details, action.payload.runId).loading = action.payload.loading
    },
    setDetailError: (
      state,
      action: PayloadAction<{ runId: string; error: string | null }>,
    ) => {
      requestState(state.details, action.payload.runId).error = action.payload.error
    },
    setDetailData: (
      state,
      action: PayloadAction<{ runId: string; data: EvaluationRunDetail }>,
    ) => {
      requestState(state.details, action.payload.runId).data = action.payload.data
    },
  },
})

export const EvaluationRunsActions = evaluationRunsSlice.actions
export const evaluationRunsReducer = evaluationRunsSlice.reducer
