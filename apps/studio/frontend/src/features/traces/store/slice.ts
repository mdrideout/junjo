import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import type { TraceEvidence } from '../schemas/trace-evidence'

interface TracesState {
  serviceNames: {
    data: string[]
    loading: boolean
    error: boolean
  }
  traceEvidence: {
    [traceId: string]: TraceEvidence
  }
  traceEvidenceRequest: {
    traceId: string | null
    loading: boolean
    error: boolean
  }
}

const initialState: TracesState = {
  serviceNames: {
    data: [],
    loading: false,
    error: false,
  },
  traceEvidence: {},
  traceEvidenceRequest: {
    traceId: null,
    loading: false,
    error: false,
  },
}

export const tracesSlice = createSlice({
  name: 'tracesState',
  initialState,
  reducers: {
    // Listener Middleware Triggers
    fetchTraceEvidence: {
      reducer: () => {
        // Handled by listener middleware
      },
      prepare: (payload: { traceId: string | undefined }) => ({ payload }),
    },
    fetchServiceNames: () => {
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

    // Trace Evidence Request Actions
    traceEvidenceRequestStarted: (state, action: PayloadAction<{ traceId: string }>) => {
      state.traceEvidenceRequest = {
        traceId: action.payload.traceId,
        loading: true,
        error: false,
      }
    },
    traceEvidenceRequestSucceeded: (
      state,
      action: PayloadAction<{ traceId: string; data: TraceEvidence }>,
    ) => {
      state.traceEvidence[action.payload.traceId] = action.payload.data
      if (state.traceEvidenceRequest.traceId === action.payload.traceId) {
        state.traceEvidenceRequest.loading = false
        state.traceEvidenceRequest.error = false
      }
    },
    traceEvidenceRequestFailed: (state, action: PayloadAction<{ traceId: string }>) => {
      if (state.traceEvidenceRequest.traceId === action.payload.traceId) {
        state.traceEvidenceRequest.loading = false
        state.traceEvidenceRequest.error = true
      }
    },
  },
})

export const TracesStateActions = tracesSlice.actions
export default tracesSlice.reducer
