import { describe, expect, it } from 'vitest'
import workflowDetailReducer, { WorkflowDetailStateActions } from './slice'

describe('workflow detail state', () => {
  it('increments the failures trigger deterministically', () => {
    let state = workflowDetailReducer(undefined, WorkflowDetailStateActions.setOpenFailuresTrigger())
    expect(state.openFailuresTrigger).toBe(1)

    state = workflowDetailReducer(state, WorkflowDetailStateActions.setOpenFailuresTrigger())
    expect(state.openFailuresTrigger).toBe(2)

    state = workflowDetailReducer(state, WorkflowDetailStateActions.initializeWorkflowRoute(null))
    expect(state.openFailuresTrigger).toBeNull()
  })
})
