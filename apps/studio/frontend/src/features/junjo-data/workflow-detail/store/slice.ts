import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { OtelSpan } from '../../../traces/schemas/schemas'
import type {
  StateEventIdentity,
  StateEventSelection,
} from '../state-event-identity'

interface WorkflowDetailState {
  activeSpan: OtelSpan | null
  activeStateEvent: StateEventSelection | null
  stateEventScrollTarget: StateEventIdentity | null
  openFailuresTrigger: number | null
}

const initialState: WorkflowDetailState = {
  activeSpan: null,
  activeStateEvent: null,
  stateEventScrollTarget: null,
  openFailuresTrigger: null,
}

export const otelSlice = createSlice({
  name: 'workflowDetailState',
  initialState,
  reducers: {
    setActiveSpan: (state, action: PayloadAction<OtelSpan | null>) => {
      state.activeSpan = action.payload
    },
    initializeWorkflowRoute: (state, action: PayloadAction<OtelSpan | null>) => {
      state.activeSpan = action.payload
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
