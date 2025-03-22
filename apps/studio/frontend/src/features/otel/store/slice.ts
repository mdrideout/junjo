import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { WorkflowSpansE2EResponse } from './schemas'

interface OtelState {
  data: WorkflowSpansE2EResponse
  loading: boolean
  error: boolean
}

const initialState: OtelState = {
  data: {
    workflowLineage: [],
    workflowSpans: [],
  },
  loading: false,
  error: false,
}

export const otelSlice = createSlice({
  name: 'otelState',
  initialState,
  reducers: {
    fetchData: (_state, _action: PayloadAction<null>) => {
      // Handled by listener middleware
    },
    setData: (state, action: PayloadAction<WorkflowSpansE2EResponse>) => {
      state.data = action.payload
    },
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload
    },
    setError: (state, action: PayloadAction<boolean>) => {
      state.error = action.payload
    },
  },
})

export const OtelStateActions = otelSlice.actions

// Selectors
export const selectWorkflowSpans = (state: { otelState: OtelState }) => state.otelState.data.workflowSpans
export const selectWorkflowLineage = (state: { otelState: OtelState }) => state.otelState.data.workflowLineage
export const selectLoading = (state: { otelState: OtelState }) => state.otelState.loading
export const selectError = (state: { otelState: OtelState }) => state.otelState.error

// Reducer
export default otelSlice.reducer
