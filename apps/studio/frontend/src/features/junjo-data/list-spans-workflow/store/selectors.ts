import { createSelector } from '@reduxjs/toolkit'
import { RootState } from '../../../../root-store/store'
import { OtelSpan } from '../../../otel/schemas/schemas'

// Base Selector
export const selectWorkflowExecutionsState = (state: RootState) => state.workflowSpanListState

// Selectors
export const selectWorkflowSpanList = (state: RootState) => state.workflowSpanListState.workflowSpanList
export const selectWorkflowSpanListLoading = (state: RootState) => state.workflowSpanListState.loading
export const selectWorkflowSpanListError = (state: RootState) => state.workflowSpanListState.error

// Memoized Selectors
export const selectWorkflowSpan = createSelector(
  [selectWorkflowSpanList, (_state: RootState, props: { spanID: string | undefined }) => props.spanID],
  (workflowExecutions, spanID): OtelSpan | undefined => {
    if (!spanID) return undefined
    return workflowExecutions.find((item) => item.span_id === spanID)
  },
)

export const selectPrevWorkflowSpan = (
  state: RootState,
  props: { serviceName: string | undefined; spanID: string | undefined },
) => {
  const workflowSpans = selectWorkflowSpanList(state)
  if (!workflowSpans) return undefined
  const spanIndex = workflowSpans.findIndex((item) => item.span_id === props.spanID)
  if (spanIndex === -1 || spanIndex === 0) return undefined
  return workflowSpans[spanIndex - 1]
}

export const selectNextWorkflowSpan = (
  state: RootState,
  props: { serviceName: string | undefined; spanID: string | undefined },
) => {
  const workflowSpans = selectWorkflowSpanList(state)
  if (!workflowSpans) return undefined
  const spanIndex = workflowSpans.findIndex((item) => item.span_id === props.spanID)
  if (spanIndex === -1 || spanIndex === workflowSpans.length - 1) return undefined
  return workflowSpans[spanIndex + 1]
}
