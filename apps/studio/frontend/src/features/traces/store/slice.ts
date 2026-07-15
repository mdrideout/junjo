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
  loading: boolean
  error: boolean
}

const initialState: TracesState = {
  serviceNames: {
    data: [],
    loading: false,
    error: false,
  },
  traceEvidence: {},
  loading: false,
  error: false,
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

    // Traces Data Actions
    setTraceEvidenceData: (state, action: PayloadAction<{ traceId: string; data: TraceEvidence }>) => {
      state.traceEvidence[action.payload.traceId] = action.payload.data
    },
    setTracesLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload
    },
    setTracesError: (state, action: PayloadAction<boolean>) => {
      state.error = action.payload
    },
  },
})

export const TracesStateActions = tracesSlice.actions
export default tracesSlice.reducer
