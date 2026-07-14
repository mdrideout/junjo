import { createSelector, createSelectorCreator, lruMemoize } from '@reduxjs/toolkit'
import { RootState } from '../../../root-store/store'
import { JunjoSpanType, OtelSpan } from '../../traces/schemas/schemas'
import {
  selectActiveStateEvent,
  selectWorkflowDetailActiveSpan,
} from '../../junjo-data/workflow-detail/store/selectors'
import { wrapSpan } from '../utils/span-accessor'

export const selectTracesState = (state: RootState) => state.tracesState
export const selectTraceSpans = (state: RootState) => state.tracesState.traceSpans
export const selectTracesLoading = (state: RootState) => state.tracesState.loading
export const selectTracesError = (state: RootState) => state.tracesState.error

// Selectors - Service Names
export const selectServiceNamesLoading = (state: RootState) => state.tracesState.serviceNames.loading
export const selectServiceNamesError = (state: RootState) => state.tracesState.serviceNames.error
export const selectServiceNames = (state: RootState) => state.tracesState.serviceNames.data

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
    return traceSpans[traceId] ?? []
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
        const spanType = wrapSpan(span).junjoSpanType
        if (spanType === JunjoSpanType.WORKFLOW || spanType === JunjoSpanType.SUBFLOW) {
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
 * Select Workflow Span By Store ID
 * Allows for the selection of a workflow span for a given storeId
 */
export const selectWorkflowSpanByStoreId = createSelector(
  [selectTraceSpansForTraceId, (_state: RootState, props: { storeId: string | undefined }) => props.storeId],
  (traceSpans, storeId): OtelSpan | undefined => {
    if (!traceSpans || !storeId) return undefined

    return traceSpans.find((span) => wrapSpan(span).workflowStoreId === storeId)
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
      // Check if the span is a junjo span (and not 'other' which is an empty string enum (falsy)), return it
      if (wrapSpan(span).isJunjoSpan) {
        return span
      }

      // if not, get the parent span and recursively call this function to check it
      const parentSpan = allSpans.find((s) => s.span_id === span.parent_span_id)
      if (parentSpan) {
        return recursivelyCheckParentSpansForJunjoSpan(parentSpan)
      }

      // If no parent span is found, break the recursion
      return undefined
    }
    // Start the recursion with the event span
    return recursivelyCheckParentSpansForJunjoSpan(activeSpan)
  },
)

/**
 * Select Active Span's Junjo Workflow Span
 * Allows for the selection of a workflow span from the active span.
 *
 * The input selectors select all spans umbrellad under the top-level workflow span.
 * The current span's workflow span may be a lower level subflow or a workflow span.
 *
 * If: the active span is a workflow span, return it
 * Else: Recursively check the parent spans to find the workflow span
 */
export const selectActiveSpanJunjoWorkflow = createSelector(
  [selectWorkflowDetailActiveSpan, selectTraceSpans],
  (activeSpan, traces): OtelSpan | undefined => {
    if (!activeSpan) return undefined

    // Get all Otel Spans for the active span's trace
    const allSpans: OtelSpan[] = traces[activeSpan.trace_id]

    // Recursively check the parent spans to find the first workflow / subflow span
    function recursivelyCheckParentSpansForWorkflowSpan(span: OtelSpan): OtelSpan | undefined {
      // Check if the span is a workflow or subflow, return it
      const spanType = wrapSpan(span).junjoSpanType
      if (spanType === JunjoSpanType.WORKFLOW || spanType === JunjoSpanType.SUBFLOW) {
        // Add to the beginning of the chain and continue traversing
        return span
      }

      // if not, get the parent span and recursively call this function to check it
      const parentSpan = allSpans.find((s) => s.span_id === span.parent_span_id)
      if (parentSpan) {
        return recursivelyCheckParentSpansForWorkflowSpan(parentSpan)
      }

      // If no parent span is found, break the recursion
      return undefined
    }
    // Start the recursion with the event span
    return recursivelyCheckParentSpansForWorkflowSpan(activeSpan)
  },
)

/**
 * Select Span Child Spans
 * Given a traceId and spanId, return all child spans of that span (inclusive)
 */
export const selectSpanAndChildren = createSelector(
  [selectTraceSpansForTraceId, (_state: RootState, props: { spanId: string | undefined }) => props.spanId],
  (traceSpans, spanId): OtelSpan[] => {
    if (!traceSpans || !spanId) return [] // Stable empty array reference

    // Find starting span without calling another selector directly inside result func
    const startingSpan = traceSpans.find((item) => item.span_id === spanId)
    if (!startingSpan) return [] // Stable empty array reference

    // Logic to find children - this computation only runs if workflowsData or props change
    const foundSpans: OtelSpan[] = [startingSpan]
    const queue: OtelSpan[] = [startingSpan]
    const visited = new Set<string>() // Prevent cycles
    visited.add(startingSpan.span_id)

    while (queue.length > 0) {
      const currentSpan = queue.shift()!
      // .filter creates a new array, but it's okay inside the memoized function
      const childSpans = traceSpans.filter((s) => s.parent_span_id === currentSpan.span_id)
      for (const child of childSpans) {
        if (!visited.has(child.span_id)) {
          foundSpans.push(child)
          queue.push(child)
          visited.add(child.span_id)
        }
      }
    }
    // The returned 'children' array reference is memoized by createSelector
    return foundSpans
  },
)

/**
 * Select Trace Spans With Failures
 * For a given trace, create a list of all spans that carry Junjo failure signals.
 * @returns {OtelSpan[]} sorted by their timeUnixNano
 */
export const selectTraceFailureSpans = createSelector(
  [selectTraceSpansForTraceId],
  (traceSpans): OtelSpan[] => {
    return traceSpans.filter((span) => wrapSpan(span).hasFailureSignal)
  },
)

/**
 * Select: Active Store ID
 * This selector finds the store ID of the store that the current span acts on.
 *
 * If a state event is selected, use the store that event actually mutated.
 * Otherwise, default to the selected workflow or subflow span's own store.
 */
export const selectActiveStoreID = createSelector(
  [selectActiveStateEvent, selectWorkflowDetailActiveSpan, selectActiveSpanJunjoWorkflow],
  (activeStateEvent, activeSpan, activeWorkflowSpan): string | undefined => {
    if (!activeSpan) return undefined
    if (!activeWorkflowSpan) return undefined

    // If there is an active set_state event, return its store ID
    if (activeStateEvent) {
      return activeStateEvent.storeId
    }

    // Otherwise, default to the active workflow or subflow span's own store.
    return activeWorkflowSpan ? wrapSpan(activeWorkflowSpan).workflowStoreId : undefined
  },
)
