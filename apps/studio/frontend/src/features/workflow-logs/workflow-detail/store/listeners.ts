import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import { AppDispatch, RootState } from '../../../../root-store/store'
import { WorkflowDetailStateActions } from './slice'
import { selectFirstStateEventInSpanOrChildren } from '../../../otel/store/selectors'

export const workflowDetailListenerMiddleware = createListenerMiddleware()
const startListener = workflowDetailListenerMiddleware.startListening.withTypes<RootState, AppDispatch>()

startListener({
  actionCreator: WorkflowDetailStateActions.handleSetActiveSpan,
  effect: async (action, { getState, dispatch }) => {
    const span = action.payload

    // Set the active span in the state
    dispatch(WorkflowDetailStateActions.setActiveSpan(span))

    const firstSetStateEvent = selectFirstStateEventInSpanOrChildren(getState(), {
      serviceName: span.service_name,
      spanID: span.span_id,
    })

    // If a set_state event is found, set it as the active set_state event
    // and scroll to the event
    if (firstSetStateEvent) {
      dispatch(WorkflowDetailStateActions.setActiveSetStateEvent(firstSetStateEvent))
      dispatch(WorkflowDetailStateActions.setScrollToStateEventId(firstSetStateEvent.attributes.id))
    }
    // If no set_state event is found, set the active set_state event to null
    // and scroll to the span
    else {
      dispatch(WorkflowDetailStateActions.setActiveSetStateEvent(null))
      dispatch(WorkflowDetailStateActions.setScrollToSpanId(span.span_id))
    }
  },
})
