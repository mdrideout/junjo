import { createSelector } from '@reduxjs/toolkit'
import type { RootState } from '../../../../root-store/store'

// Selectors - Workflow Detail
export const selectActiveStateEvent = (state: RootState) => state.workflowDetailState.activeStateEvent
export const selectWorkflowDetailActiveSpan = createSelector(
  [
    (state: RootState) => state.workflowDetailState.activeSpanIdentity,
    (state: RootState) => state.tracesState.traceEvidence,
  ],
  (identity, evidenceByTraceId) => {
    if (identity === null) return undefined
    return evidenceByTraceId[identity.traceId]?.spans.find(
      (span) => span.span_id === identity.spanId,
    )
  },
)
