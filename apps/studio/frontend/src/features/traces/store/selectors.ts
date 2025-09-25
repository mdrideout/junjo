import { createSelector, createSelectorCreator, lruMemoize } from '@reduxjs/toolkit'
import { RootState } from '../../../root-store/store'
import { JunjoSpanType, OtelSpan } from '../../otel/schemas/schemas'
import { selectWorkflowDetailActiveSpan } from '../../otel/store/selectors'

export const selectTracesState = (state: RootState) => state.tracesState
export const selectTraceSpans = (state: RootState) => state.tracesState.traceSpans
export const selectTracesLoading = (state: RootState) => state.tracesState.loading
export const selectTracesError = (state: RootState) => state.tracesState.error

/**
 * Selector: Select Span By Id
 * Given a traceId and spanId, return the span with that id
 */
export const selectSpanById = createSelector(
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

/**
 * Selector: Select Trace Spans
 * Returns all spans for a given traceId
 */
export const selectTraceSpansForTraceId = createSelector(
  [
    (state: RootState) => state.tracesState.traceSpans,
    (_state: RootState, props: { traceId: string | undefined }) => props.traceId,
  ],
  (traceSpans, traceId): OtelSpan[] => {
    if (!traceId) {
      return []
    }
    return traceSpans[traceId]
  },
)

/**
 * Workflow Chain Equality Check
 * Purpose: Avoid re-rendering every time the active span changes
 *          and the workflow chain is the same.
 */
const workflowChainListEquality = (prevList: OtelSpan[], nextList: OtelSpan[]) => {
  // console.log(`Checking workflow chain equality...`)
  // console.log('Previous List: ', prevList)
  // console.log('Next List: ', nextList)

  if (!prevList || !nextList) return false

  // Check if the lengths are different
  if (prevList.length !== nextList.length) return false

  // Check if the elements are different
  for (let i = 0; i < prevList.length; i++) {
    if (prevList[i].span_id !== nextList[i].span_id) return false
  }
  // If all checks pass, the lists are equal
  return true
}

/**
 * Workflow Chain Selector Creator
 */
const createWorkflowChainSelector = createSelectorCreator(lruMemoize, workflowChainListEquality)

/**
 * Identify Span Workflow Chain
 * Returns a chain of workflows and subflows that the span is part of.
 * For example, this node may be part of Workflow -> Subflow -> Subflow
 *
 * Recursively checks the parent spans to find workflow / subflow spans
 * to identify the entire chain of subflows.
 *
 * This can be used to render all of the workflows / subflows leading
 * to this node
 *
 * @returns {OtelSpan | undefined}
 */
export const identifySpanWorkflowChain = createWorkflowChainSelector(
  [
    (state: RootState) => state.tracesState.traceSpans,
    (_state: RootState, props: { traceId: string | undefined }) => props.traceId,
    (_state: RootState, props: { workflowSpanId: string | undefined }) => props.workflowSpanId,
    selectWorkflowDetailActiveSpan,
  ],
  // Result function now receives individual values, not the props object
  (traceSpans, traceId, workflowSpanId, activeSpan): OtelSpan[] => {
    // Initial array
    const workflowSpanChain: OtelSpan[] = []

    // Exit early if missing params
    if (!traceSpans || !traceId || !workflowSpanId) {
      console.error('Span Workflow Chain Selector missing params.')
      return workflowSpanChain
    }

    // All Trace Spans
    const allTraceSpans: OtelSpan[] = traceSpans[traceId]
    if (!allTraceSpans) {
      return workflowSpanChain
    }

    // The provided workflow span id is for the top-level workflow
    const topLevelWorkflowSpan: OtelSpan | undefined = allTraceSpans.find((s) => s.span_id === workflowSpanId)
    if (!topLevelWorkflowSpan) {
      return workflowSpanChain
    }

    // If we have an active span, we need to find the workflow chain
    if (activeSpan) {
      // Ensure this span exists in the trace spans
      if (!allTraceSpans.find((s) => s.span_id === activeSpan.span_id)) {
        // Return stable empty array reference if starting span not found in data
        return workflowSpanChain
      }

      // Recursively check the parent spans to find the first workflow / subflow span
      function recursivelyBuildWorkflowSpanChain(span: OtelSpan): OtelSpan | undefined {
        // Check if the span is a workflow or subflow, if so, return it
        if (
          span.junjo_span_type === JunjoSpanType.WORKFLOW ||
          span.junjo_span_type === JunjoSpanType.SUBFLOW
        ) {
          // Add to the beginning of the chain and continue traversing
          workflowSpanChain.unshift(span)
        }

        // if not, get the parent span and recursively call this function to check it
        const parentSpan = allTraceSpans.find((s) => s.span_id === span.parent_span_id)
        if (parentSpan) {
          return recursivelyBuildWorkflowSpanChain(parentSpan)
        }

        // If no parent span is found, break the recursion
        return undefined
      }
      // Start the recursion with the event span
      recursivelyBuildWorkflowSpanChain(activeSpan)
    }

    // If the span chain is empty, add the top-level workflow span
    // Otherwise, the recursive function will add it.
    if (workflowSpanChain.length === 0) {
      workflowSpanChain.push(topLevelWorkflowSpan)
    }

    return workflowSpanChain
  },
  {
    memoizeOptions: {
      resultEqualityCheck: workflowChainListEquality,
    },
  },
)

/**
 * Select Active Span's First Junjo Parent Span
 * For the active span, find the first parent span that is a Junjo span (not 'other').
 * This includes the starting span itself.
 * This allows is to quickly find the closest parent Junjo span that contains this span
 * to identify workflows, subflows, nodes, etc.
 * @returns {OtelSpan | undefined}
 */
export const selectActiveSpanFirstJunjoParent = createSelector(
  [selectWorkflowDetailActiveSpan, selectTraceSpans],
  (activeSpan, traces): OtelSpan | undefined => {
    if (!activeSpan) return undefined

    // Get all Otel Spans for the active span's trace
    const allSpans: OtelSpan[] = traces[activeSpan.trace_id]

    // Recursively check the parent spans to find the first junjo span
    function recursivelyCheckParentSpansForJunjoSpan(span: OtelSpan): OtelSpan | undefined {
      console.log('Checking for parent span: ', span)
      // Check if the span is a junjo span (and not 'other' which is an empty string enum (falsy)), return it
      if (span.junjo_span_type) {
        console.log('Found junjo span: ', span)
        return span
      }

      // if not, get the parent span and recursively call this function to check it
      const parentSpan = allSpans.find((s) => s.span_id === span.parent_span_id)
      if (parentSpan) {
        console.log('Parent span found: ', parentSpan)
        return recursivelyCheckParentSpansForJunjoSpan(parentSpan)
      }

      console.log('No parent span found')

      // If no parent span is found, break the recursion
      return undefined
    }
    // Start the recursion with the event span
    return recursivelyCheckParentSpansForJunjoSpan(activeSpan)
  },
)
