import { createSelector } from '@reduxjs/toolkit'
import { RootState } from '../../../../root-store/store'
import { OtelSpan } from '../../../otel/schemas/schemas'
// Base Selector
export const selectWorkflowExecutionsState = (state: RootState) => state.workflowExecutionsState
// Selectors
export const selectWorkflowExecutions = (state: RootState) => state.workflowExecutionsState.workflowExecutions
export const selectWorkflowExecutionsLoading = (state: RootState) => state.workflowExecutionsState.loading
export const selectWorkflowExecutionsError = (state: RootState) => state.workflowExecutionsState.error
// Memoized Selectors
export const selectWorkflowSpan = createSelector(
  [selectWorkflowExecutions, (_state: RootState, props: { spanID: string | undefined }) => props.spanID],
  (workflowExecutions, spanID): OtelSpan | undefined => {
    if (!spanID) return undefined
    return workflowExecutions.find((item) => item.span_id === spanID)
  },
)
export const selectPrevWorkflowSpanID = (
  state: RootState,
  props: { serviceName: string | undefined; spanID: string | undefined },
) => {
  const workflowSpans = selectWorkflowExecutions(state)
  if (!workflowSpans) return undefined
  const spanIndex = workflowSpans.findIndex((item) => item.span_id === props.spanID)
  if (spanIndex === -1 || spanIndex === 0) return undefined
  return workflowSpans[spanIndex - 1].span_id
}
export const selectNextWorkflowSpanID = (
  state: RootState,
  props: { serviceName: string | undefined; spanID: string | undefined },
) => {
  const workflowSpans = selectWorkflowExecutions(state)
  if (!workflowSpans) return undefined
  const spanIndex = workflowSpans.findIndex((item) => item.span_id === props.spanID)
  if (spanIndex === -1 || spanIndex === workflowSpans.length - 1) return undefined
  return workflowSpans[spanIndex + 1].span_id
}
