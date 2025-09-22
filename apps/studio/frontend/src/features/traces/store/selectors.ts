import { createSelector } from '@reduxjs/toolkit'
import { RootState } from '../../../root-store/store'
import { OtelSpan } from '../../otel/schemas/schemas'

export const selectTracesState = (state: RootState) => state.tracesState

export const selectTracesLoading = (state: RootState) => state.tracesState.loading
export const selectTracesError = (state: RootState) => state.tracesState.error

export const selectWorkflowSpan = createSelector(
  [
    (state: RootState) => state.tracesState.traceSpans,
    (_state: RootState, props: { traceId: string | undefined; spanId: string | undefined }) => props.traceId,
    (_state: RootState, props: { traceId: string | undefined; spanId: string | undefined }) => props.spanId,
  ],
  (traceSpans, traceId, spanId): OtelSpan | undefined => {
    if (!traceId || !spanId) {
      return undefined
    }
    const spans = traceSpans[traceId]
    if (!spans) {
      return undefined
    }
    return spans.find((item) => item.span_id === spanId)
  },
)
