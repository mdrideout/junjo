import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import { AppDispatch, RootState } from '../../../../root-store/store'
import { WorkflowExecutionsStateActions } from './slice'
import { getSpansTypeWorkflow } from '../fetch/get-spans-type-workflow'

export const workflowExecutionsListenerMiddleware = createListenerMiddleware()
const startListener = workflowExecutionsListenerMiddleware.startListening.withTypes<RootState, AppDispatch>()

startListener({
  actionCreator: WorkflowExecutionsStateActions.fetchSpansTypeWorkflow,
  effect: async (action, { getState, dispatch }) => {
    const { loading } = getState().workflowSpanListState
    if (loading) return

    dispatch(WorkflowExecutionsStateActions.setWorkflowExecutionsError(false))
    dispatch(WorkflowExecutionsStateActions.setWorkflowExecutionsLoading(true))

    try {
      const serviceName = action.payload
      const data = await getSpansTypeWorkflow(serviceName)
      dispatch(WorkflowExecutionsStateActions.setWorkflowExecutionsData(data))
    } catch (error) {
      dispatch(WorkflowExecutionsStateActions.setWorkflowExecutionsError(true))
    } finally {
      dispatch(WorkflowExecutionsStateActions.setWorkflowExecutionsLoading(false))
    }
  },
})
