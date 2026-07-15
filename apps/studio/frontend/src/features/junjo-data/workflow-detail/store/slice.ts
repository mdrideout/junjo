import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import type { OtelSpan } from '../../../traces/schemas/schemas'
import type {
  StateEventIdentity,
  StateEventSelection,
} from '../state-event-identity'

interface WorkflowDetailState {
  activeSpanIdentity: SpanSelection | null
  activeStateEvent: StateEventSelection | null
  stateEventScrollTarget: StateEventIdentity | null
  openFailuresTrigger: number | null
}

const initialState: WorkflowDetailState = {
  activeSpanIdentity: null,
  activeStateEvent: null,
  stateEventScrollTarget: null,
  openFailuresTrigger: null,
}

export const otelSlice = createSlice({
  name: 'workflowDetailState',
  initialState,
  reducers: {
    selectSpan: (state, action: PayloadAction<SpanSelection | null>) => {
      state.activeSpanIdentity = action.payload
    },
    initializeWorkflowRoute: (state, action: PayloadAction<SpanSelection | null>) => {
      state.activeSpanIdentity = action.payload
      state.activeStateEvent = null
      state.stateEventScrollTarget = null
      state.openFailuresTrigger = null
    },
    setActiveStateEvent: (state, action: PayloadAction<StateEventSelection | null>) => {
      state.activeStateEvent = action.payload
      state.stateEventScrollTarget = null
    },
    setStateEventScrollTarget: (state, action: PayloadAction<StateEventIdentity | null>) => {
      state.stateEventScrollTarget = action.payload
    },
    setOpenFailuresTrigger: (state) => {
      state.openFailuresTrigger = Date.now()
    },
  },
})

export const WorkflowDetailStateActions = otelSlice.actions
export default otelSlice.reducer

export interface SpanSelection {
  traceId: string
  spanId: string
}

export function spanSelection(span: OtelSpan): SpanSelection {
  return { traceId: span.trace_id, spanId: span.span_id }
}
