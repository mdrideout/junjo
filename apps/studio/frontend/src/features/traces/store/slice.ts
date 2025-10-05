import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { OtelSpan } from '../../traces/schemas/schemas'

interface TracesState {
  serviceNames: {
    data: string[]
    loading: boolean
    error: boolean
  }
  traceSpans: {
    [traceId: string]: OtelSpan[]
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
  traceSpans: {},
  loading: false,
  error: false,
}

export const tracesSlice = createSlice({
  name: 'tracesState',
  initialState,
  reducers: {
    // Listener Middleware Triggers
    fetchSpansByTraceId: (_state, _action: PayloadAction<{ traceId: string | undefined }>) => {
      // Handled by listener middleware
    },
    fetchServiceNames: (_state) => {
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
    setTracesData: (state, action: PayloadAction<{ traceId: string; data: OtelSpan[] }>) => {
      state.traceSpans[action.payload.traceId] = action.payload.data
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
