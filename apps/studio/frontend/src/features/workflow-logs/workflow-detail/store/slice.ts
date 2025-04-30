import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { JunjoSetStateEvent, OtelSpan } from '../../../otel/store/schemas'

interface WorkflowDetailState {
  activeSpan: OtelSpan | null
  activeSetStateEvent: JunjoSetStateEvent | null
  scrollToSpanId: string | null
  scrollToStateEventId: string | null
  openExceptionsTrigger: number | null
}

const initialState: WorkflowDetailState = {
  activeSpan: null,
  activeSetStateEvent: null,
  scrollToSpanId: null,
  scrollToStateEventId: null,
  openExceptionsTrigger: null,
}

export const otelSlice = createSlice({
  name: 'workflowDetailState',
  initialState,
  reducers: {
    setActiveSpan: (state, action: PayloadAction<OtelSpan | null>) => {
      state.activeSpan = action.payload
    },
    setActiveSetStateEvent: (state, action: PayloadAction<JunjoSetStateEvent | null>) => {
      state.activeSetStateEvent = action.payload
    },
    setScrollToSpanId: (state, action: PayloadAction<string | null>) => {
      state.scrollToSpanId = action.payload
    },
    setScrollToStateEventId: (state, action: PayloadAction<string | null>) => {
      state.scrollToStateEventId = action.payload
    },
    setOpenExceptionsTrigger: (state) => {
      // Set the openExceptionsTrigger to a new value
      state.openExceptionsTrigger = Date.now()
    },
  },
})

export const WorkflowDetailStateActions = otelSlice.actions
export default otelSlice.reducer
