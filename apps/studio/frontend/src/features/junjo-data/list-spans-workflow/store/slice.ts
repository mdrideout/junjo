import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { OtelSpan } from '../../../traces/schemas/schemas'

interface WorkflowSpanListState {
  workflowSpanList: OtelSpan[]
  loading: boolean
  error: string | null
}

const initialState: WorkflowSpanListState = {
  workflowSpanList: [],
  loading: false,
  error: null,
}

export const workflowSpanListSlice = createSlice({
  name: 'workflowSpanListState',
  initialState,
  reducers: {
    // Listener Middleware Triggers
    fetchSpansTypeWorkflow: {
      reducer: () => {
        // Handled by listener middleware
      },
      prepare: (payload: string) => ({ payload }),
    },

    setWorkflowExecutionsData: (state, action: PayloadAction<OtelSpan[]>) => {
      state.workflowSpanList = action.payload
    },
    setWorkflowExecutionsLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload
    },
    setWorkflowExecutionsError: (state, action: PayloadAction<string | null>) => {
      state.error = action.payload
    },
  },
})

export const WorkflowExecutionsStateActions = workflowSpanListSlice.actions
export default workflowSpanListSlice.reducer
