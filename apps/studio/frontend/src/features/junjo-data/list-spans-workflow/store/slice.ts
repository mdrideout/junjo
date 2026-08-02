import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { OtelSpan } from '../../../traces/schemas/schemas'

export interface WorkflowSpanListState {
  listServiceName: string | null
  workflowSpanList: OtelSpan[]
  loading: boolean
  error: string | null
}

export const initialWorkflowSpanListState: WorkflowSpanListState = {
  listServiceName: null,
  workflowSpanList: [],
  loading: false,
  error: null,
}

export const workflowSpanListSlice = createSlice({
  name: 'workflowSpanListState',
  initialState: initialWorkflowSpanListState,
  reducers: {
    // Listener Middleware Triggers
    fetchSpansTypeWorkflow: {
      reducer: () => {
        // Handled by listener middleware
      },
      prepare: (payload: string) => ({ payload }),
    },

    loadStarted: (state, action: PayloadAction<{ serviceName: string }>) => {
      state.listServiceName = action.payload.serviceName
      state.workflowSpanList = []
      state.loading = true
      state.error = null
    },
    loadSucceeded: (state, action: PayloadAction<{ serviceName: string; data: OtelSpan[] }>) => {
      if (state.listServiceName !== action.payload.serviceName) return
      state.workflowSpanList = action.payload.data
      state.loading = false
      state.error = null
    },
    loadFailed: (state, action: PayloadAction<{ serviceName: string; error: string }>) => {
      if (state.listServiceName !== action.payload.serviceName) return
      state.loading = false
      state.error = action.payload.error
    },
  },
})

export const WorkflowExecutionsStateActions = workflowSpanListSlice.actions
export default workflowSpanListSlice.reducer
