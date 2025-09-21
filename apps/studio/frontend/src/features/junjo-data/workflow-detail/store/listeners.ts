import { createListenerMiddleware } from '@reduxjs/toolkit/react'
import { AppDispatch, RootState } from '../../../../root-store/store'
import { WorkflowDetailStateActions } from './slice'
import { selectFirstJunjoParentSpan } from '../../../otel/store/selectors'

export const workflowDetailListenerMiddleware = createListenerMiddleware()
const startListener = workflowDetailListenerMiddleware.startListening.withTypes<RootState, AppDispatch>()

startListener({
  actionCreator: WorkflowDetailStateActions.handleSetActiveSpan,
  effect: async (action, { getState, dispatch }) => {
    const span = action.payload
    console.log('Selected span: ', span)

    // Set the active span in the state
    dispatch(WorkflowDetailStateActions.setActiveSpan(span))

    // Find the first parent Junjo span to highlight in the diagram
    const firstJunjoSpan = selectFirstJunjoParentSpan(getState(), {
      serviceName: span.service_name,
      spanID: span.span_id,
    })

    console.log('First junjo span: ', firstJunjoSpan)

    // TODO: How does the diagram determine what to highlight? An explicitly set state value? Or infer from the active span?

    // If this is a set_state event, set it as the active set_state event
    // and scroll to the event
    // TODO: Check if this is a set state event?
    // Set and scroll?

    // // If a set_state event is found, set it as the active set_state event
    // // and scroll to the event
    // if (firstSetStateEvent) {
    //   dispatch(WorkflowDetailStateActions.setActiveSetStateEvent(firstSetStateEvent))
    //   dispatch(WorkflowDetailStateActions.setScrollToStateEventId(firstSetStateEvent.attributes.id))
    // }
    // // If no set_state event is found, set the active set_state event to null
    // // and scroll to the span
    // else {
    //   dispatch(WorkflowDetailStateActions.setActiveSetStateEvent(null))
    //   dispatch(WorkflowDetailStateActions.setScrollToSpanId(span.span_id))
    // }
  },
})

// startListener({
//   actionCreator: WorkflowDetailStateActions.handleSetActiveSetStateEvent,
//   effect: async (action, { getState, dispatch }) => {
//     console.error('NOT IMPLEMENTED')

//     // const span = action.payload

//     // // Set the active span in the state
//     // dispatch(WorkflowDetailStateActions.setActiveSpan(span))

//     // // Find the first parent Junjo span to highlight in the diagram
//     // const firstJunjoSpan = selectFirstJunjoParentSpan(getState(), {
//     //   serviceName: span.service_name,
//     //   spanID: span.span_id,
//     // })

//     // // If a set_state event is found, set it as the active set_state event
//     // // and scroll to the event
//     // if (firstSetStateEvent) {
//     //   dispatch(WorkflowDetailStateActions.setActiveSetStateEvent(firstSetStateEvent))
//     //   dispatch(WorkflowDetailStateActions.setScrollToStateEventId(firstSetStateEvent.attributes.id))
//     // }
//     // // If no set_state event is found, set the active set_state event to null
//     // // and scroll to the span
//     // else {
//     //   dispatch(WorkflowDetailStateActions.setActiveSetStateEvent(null))
//     //   dispatch(WorkflowDetailStateActions.setScrollToSpanId(span.span_id))
//     // }
//   },
// })
