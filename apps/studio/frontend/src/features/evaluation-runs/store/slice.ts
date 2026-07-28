import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import type {
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
  lists: Record<string, EvaluationRequestState<EvaluationRunListPage>>
  details: Record<string, EvaluationRequestState<EvaluationRunDetail>>
}

export const initialEvaluationRunsState: EvaluationRunsState = {
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
    fetchEvaluationRuns: {
      reducer: () => {
        // Listener middleware owns the request.
      },
      prepare: (query: EvaluationRunListQuery) => ({ payload: query }),
    },
    fetchEvaluationRun: {
      reducer: () => {
        // Listener middleware owns the request.
      },
      prepare: (runId: string) => ({ payload: runId }),
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
