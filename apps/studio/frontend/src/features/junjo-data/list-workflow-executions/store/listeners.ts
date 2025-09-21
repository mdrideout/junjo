import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import { AppDispatch, RootState } from '../../../../root-store/store'
import { WorkflowExecutionsStateActions } from './slice'
import { getWorkflowExecutions } from '../fetch/get-workflow-executions'

export const workflowExecutionsListenerMiddleware = createListenerMiddleware()
const startListener = workflowExecutionsListenerMiddleware.startListening.withTypes<RootState, AppDispatch>()

startListener({
  actionCreator: WorkflowExecutionsStateActions.fetchWorkflowExecutions,
  effect: async (action, { getState, dispatch }) => {
    const { loading } = getState().workflowExecutionsState
    if (loading) return

    dispatch(WorkflowExecutionsStateActions.setWorkflowExecutionsError(false))
    dispatch(WorkflowExecutionsStateActions.setWorkflowExecutionsLoading(true))

    try {
      const data = await getWorkflowExecutions()
      dispatch(WorkflowExecutionsStateActions.setWorkflowExecutionsData(data))
    } catch (error) {
      dispatch(WorkflowExecutionsStateActions.setWorkflowExecutionsError(true))
    } finally {
      dispatch(WorkflowExecutionsStateActions.setWorkflowExecutionsLoading(false))
    }
  },
})
