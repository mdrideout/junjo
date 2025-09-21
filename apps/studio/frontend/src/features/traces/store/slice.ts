import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { OtelSpan } from '../../otel/schemas/schemas'

interface TracesState {
  traceSpans: {
    [traceId: string]: OtelSpan[]
  }
  loading: boolean
  error: boolean
}

const initialState: TracesState = {
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
