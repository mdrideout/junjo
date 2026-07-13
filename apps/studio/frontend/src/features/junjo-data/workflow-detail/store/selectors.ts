import { RootState } from '../../../../root-store/store'

// Selectors - Workflow Detail
export const selectActiveSetStateEvent = (state: RootState) => state.workflowDetailState.activeSetStateEvent
export const selectWorkflowDetailActiveSpan = (state: RootState) => state.workflowDetailState.activeSpan
