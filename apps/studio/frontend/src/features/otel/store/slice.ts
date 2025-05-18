import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { WorkflowSpansE2EResponse } from '../schemas/schemas'

interface OtelState {
  serviceNames: {
    data: string[]
    loading: boolean
    error: boolean
  }
  workflows: {
    data: Partial<{ [serviceName: string]: WorkflowSpansE2EResponse }>
    loading: boolean
    error: boolean
    lastUpdated: number | null
  }
}

const initialState: OtelState = {
  serviceNames: {
    data: [],
    loading: false,
    error: false,
  },
  workflows: {
    data: {},
    loading: false,
    error: false,
    lastUpdated: null,
  },
}

export const otelSlice = createSlice({
  name: 'otelState',
  initialState,
  reducers: {
    // Listener Middleware Triggers
    fetchServiceNames: (_state) => {
      // Handled by listener middleware
    },
    fetchWorkflowsData: (_state, _action: PayloadAction<{ serviceName: string | undefined }>) => {
      // Handled by listener middleware
    },

    // Service Names Actions
    setServiceNamesData: (state, action: PayloadAction<string[]>) => {
      state.serviceNames.data = action.payload
    },
    setServiceNamesLoading: (state, action: PayloadAction<boolean>) => {
      state.serviceNames.loading = action.payload
    },
    setServiceNamesError: (state, action: PayloadAction<boolean>) => {
      state.serviceNames.error = action.payload
    },

    // Workflows Actions
    setWorkflowsData: (
      state,
      action: PayloadAction<{ serviceName: string; data: WorkflowSpansE2EResponse }>,
    ) => {
      state.workflows.data[action.payload.serviceName] = action.payload.data

      // stamp the time so we can cache
      state.workflows.lastUpdated = Date.now()
    },
    setWorkflowsLoading: (state, action: PayloadAction<boolean>) => {
      state.workflows.loading = action.payload
    },
    setWorkflowsError: (state, action: PayloadAction<boolean>) => {
      state.workflows.error = action.payload
    },
  },
})

export const OtelStateActions = otelSlice.actions
export default otelSlice.reducer
