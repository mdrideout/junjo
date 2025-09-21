import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { OtelSpan } from '../../../otel/schemas/schemas'

interface WorkflowExecutionsState {
  workflowExecutions: OtelSpan[]
  loading: boolean
  error: boolean
}

const initialState: WorkflowExecutionsState = {
  workflowExecutions: [],
  loading: false,
  error: false,
}

export const workflowExecutionsSlice = createSlice({
  name: 'workflowExecutionsState',
  initialState,
  reducers: {
    // Listener Middleware Triggers
    fetchWorkflowExecutions: (_state) => {
      // Handled by listener middleware
    },

    setWorkflowExecutionsData: (state, action: PayloadAction<OtelSpan[]>) => {
      state.workflowExecutions = action.payload
    },
    setWorkflowExecutionsLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload
    },
    setWorkflowExecutionsError: (state, action: PayloadAction<boolean>) => {
      state.error = action.payload
    },
  },
})

export const WorkflowExecutionsStateActions = workflowExecutionsSlice.actions
export default workflowExecutionsSlice.reducer
