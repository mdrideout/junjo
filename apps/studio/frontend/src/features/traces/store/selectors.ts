import { createSelector, createSelectorCreator, lruMemoize } from '@reduxjs/toolkit'
import { RootState } from '../../../root-store/store'
import {
  JunjoExceptionEventSchema,
  JunjoSetStateEvent,
  JunjoSetStateEventSchema,
  JunjoSpanType,
  OtelSpan,
} from '../../otel/schemas/schemas'
import { selectActiveSetStateEvent, selectWorkflowDetailActiveSpan } from '../../otel/store/selectors'
import { isoStringToMicrosecondsSinceEpoch } from '../../../util/duration-utils'

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
      // Check if the span is a junjo span (and not 'other' which is an empty string enum (falsy)), return it
      if (span.junjo_span_type) {
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
      if (span.junjo_span_type === JunjoSpanType.WORKFLOW || span.junjo_span_type === JunjoSpanType.SUBFLOW) {
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
 * Select Trace Spans With Exceptions
 * For a given workflow span, create a list of all of the workflow span's exceptions,
 * including its lineage and child spans.
 * @returns {OtelSpan[]} sorted by their timeUnixNano
 */
export const selectTraceExceptionSpans = createSelector(
  [selectTraceSpansForTraceId],
  (traceSpans): OtelSpan[] => {
    const exceptionSpans: OtelSpan[] = []

    for (const span of traceSpans) {
      // Basic check if events_json exists and is an array

      const hasExceptions = span.events_json.some((event) => {
        const parsedEvent = JunjoExceptionEventSchema.safeParse(event)
        return parsedEvent.success && parsedEvent.data.attributes['exception.type'] !== undefined
      })

      if (hasExceptions) {
        exceptionSpans.push(span)
      }
    }

    return exceptionSpans
  },
)

/**
 * Select Junjo set_state events by the Junjo Workflow's Store ID
 * (The unique  instance of the store for that workflow execution)
 */
export const selectStateEventsByJunjoStoreId = createSelector(
  [selectSpanAndChildren, (_state: RootState, props: { storeId: string | undefined }) => props.storeId],
  (spans, storeId): JunjoSetStateEvent[] => {
    const junjoSetStateEvents: JunjoSetStateEvent[] = []
    if (!storeId) return junjoSetStateEvents

    spans.forEach((span) => {
      // Basic check if events_json exists and is an array
      if (Array.isArray(span.events_json)) {
        span.events_json.forEach((event) => {
          try {
            // Assuming JunjoSetStateEventSchema.parse returns a newly parsed object
            const parsedEvent = JunjoSetStateEventSchema.parse(event)
            if (parsedEvent.attributes['junjo.store.id'] === storeId) {
              junjoSetStateEvents.push(parsedEvent)
            }
          } catch (error) {
            // Consider less noisy logging or specific handling
            // console.error('Error parsing event in selector:', error);
          }
        })
      }
    })

    junjoSetStateEvents.sort((a, b) => a.timeUnixNano - b.timeUnixNano)
    // createSelector memoizes this returned reference
    return junjoSetStateEvents
  },
)

/**
 * Select: Before Span State Event In Workflow
 * This selector finds the last set_state event before the current span starts in the same workflow
 *
 * 1. Find all set_state events that operate on the same store ID (meaning, we know the workflow is the same)
 * 2. Find the last set_state event before the active span starts
 *
 * @returns {JunjoSetStateEvent | undefined}
 */
export const selectBeforeSpanStateEventInWorkflow = createSelector(
  [selectWorkflowDetailActiveSpan, selectStateEventsByJunjoStoreId],
  (activeSpan, storeStateEvents): JunjoSetStateEvent | undefined => {
    if (!activeSpan) return undefined

    // Sort the store events by their timeUnixNano in ascending order
    const sortedEvents = [...storeStateEvents].sort((a, b) => a.timeUnixNano - b.timeUnixNano)

    // compute active span start in nanoseconds
    const spanStartTimeMicro = isoStringToMicrosecondsSinceEpoch(activeSpan.start_time)
    const spanStartTimeNano = spanStartTimeMicro * 1000

    // walk from the end (because in ascending order) to find the greatest event that is < spanStartTimeNano
    for (let i = sortedEvents.length - 1; i >= 0; i--) {
      if (sortedEvents[i].timeUnixNano < spanStartTimeNano) {
        return sortedEvents[i]
      }
    }
    return undefined
  },
)

/**
 * Select: Active Store ID
 * This selector finds the store ID of the store that the current span acts on.
 *
 * If: the activeSpan is a subflow, this is the parent_store.id
 *     (because the pre_run and post_run functions operate on the parent store)
 *
 * Else: For all other spans, it's the store.id of the current workflow.
 */
export const selectActiveStoreID = createSelector(
  [selectActiveSetStateEvent, selectWorkflowDetailActiveSpan, selectActiveSpanJunjoWorkflow],
  (activeSetStateEvent, activeSpan, activeWorkflowSpan): string | undefined => {
    if (!activeSpan) return undefined
    if (!activeWorkflowSpan) return undefined

    // If there is an active set_state event, return its store ID
    if (activeSetStateEvent) {
      return activeSetStateEvent.attributes['junjo.store.id']
    }

    // Else, if there is no active set_state event, return the store ID that the current span acts on
    if (activeSpan.junjo_span_type === 'subflow') {
      return activeSpan.attributes_json['junjo.workflow.parent_store.id']
    }

    // Otherwise, return the store ID of the current workflow
    return activeWorkflowSpan?.junjo_wf_store_id
  },
)

/**
 * Select State Event's Parent Span
 * @returns {OtelSpan | undefined}
 */
export const selectStateEventParentSpan = createSelector(
  [
    selectSpanAndChildren,
    (_state: RootState, props: { stateEventId: string | undefined }) => props.stateEventId,
  ],
  (childSpans, stateEventId): OtelSpan | undefined => {
    if (!stateEventId) return undefined

    // Find the span that contains this state event
    const span = childSpans.find((span) => {
      // Check if the span's events_json array contains an event with the matching id
      const hasEvent = span.events_json.some((event) => event.attributes?.id === stateEventId)
      return hasEvent
    })
    return span
  },
)

/**
 * Select All Workflow State Events
 * Given a traceId and workflowSpanId, this selector finds all state events
 * operating on the same store as the workflowSpan.
 *
 * @returns {JunjoSetStateEvent[]} sorted by their timeUnixNano
 */
export const selectAllWorkflowStateEvents = createSelector(
  [selectSpanAndChildren],
  (spans): JunjoSetStateEvent[] => {
    const junjoSetStateEvents: JunjoSetStateEvent[] = []

    spans.forEach((span) => {
      // Basic check if events_json exists and is an array
      if (Array.isArray(span.events_json)) {
        span.events_json.forEach((event) => {
          try {
            const parsedEvent = JunjoSetStateEventSchema.parse(event)
            junjoSetStateEvents.push(parsedEvent)
          } catch (error) {
            // Consider less noisy logging or specific handling
            // console.error('Error parsing event in selector:', error);
          }
        })
      }
    })

    junjoSetStateEvents.sort((a, b) => a.timeUnixNano - b.timeUnixNano)
    return junjoSetStateEvents
  },
)
