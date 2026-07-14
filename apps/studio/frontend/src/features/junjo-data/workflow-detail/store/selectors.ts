import { RootState } from '../../../../root-store/store'

// Selectors - Workflow Detail
export const selectActiveStateEvent = (state: RootState) => state.workflowDetailState.activeStateEvent
export const selectWorkflowDetailActiveSpan = (state: RootState) => state.workflowDetailState.activeSpan
