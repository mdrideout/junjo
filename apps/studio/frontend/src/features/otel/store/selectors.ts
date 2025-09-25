import { createSelector, createSelectorCreator, lruMemoize } from '@reduxjs/toolkit'
import { RootState } from '../../../root-store/store'
import {
  JunjoExceptionEventSchema,
  JunjoSetStateEvent,
  JunjoSetStateEventSchema,
  JunjoSpanType,
  OtelSpan,
} from '../schemas/schemas'
import { isoStringToMicrosecondsSinceEpoch } from '../../../util/duration-utils'

// Base Selector
export const selectOtelState = (state: RootState) => state.otelState

// Selectors - Service Names
export const selectServiceNamesLoading = (state: RootState) => state.otelState.serviceNames.loading
export const selectServiceNamesError = (state: RootState) => state.otelState.serviceNames.error
export const selectServiceNames = (state: RootState) => state.otelState.serviceNames.data

// Selectors - Workflows
export const selectWorkflowsData = (state: RootState) => state.otelState.workflows.data
export const selectWorkflowsLoading = (state: RootState) => state.otelState.workflows.loading
export const selectWorkflowsError = (state: RootState) => state.otelState.workflows.error

// Selectors - Workflow Detail
export const selectActiveSetStateEvent = (state: RootState) => state.workflowDetailState.activeSetStateEvent
export const selectWorkflowDetailActiveSpan = (state: RootState) => state.workflowDetailState.activeSpan

// --- Memoized Selectors ---
export const selectServiceWorkflows = createSelector(
  [selectWorkflowsData, (_state: RootState, props: { serviceName: string | undefined }) => props.serviceName],
  (workflowsData, serviceName) => {
    if (!serviceName) return []
    const serviceData = workflowsData[serviceName]
    if (!serviceData) return []

    // Filter creates a new array, but only when input workflowsData or props change
    return serviceData.workflowSpans.filter((item) => item.junjo_span_type === 'workflow')
  },
)

export const selectWorkflowSpan = createSelector(
  [
    selectWorkflowsData,
    (_state: RootState, props: { serviceName: string | undefined; spanID: string | undefined }) => props,
  ],
  (workflowsData, props): OtelSpan | undefined => {
    const serviceData = workflowsData[props.serviceName ?? '']
    if (!serviceData || !props.spanID) return undefined
    return serviceData.workflowSpans.find((item) => item.span_id === props.spanID)
  },
)

// Direct children only
export const selectSpanChildren = createSelector(
  [
    selectWorkflowsData,
    (_state: RootState, props: { serviceName: string | undefined; spanID: string | undefined }) => props,
  ],
  (workflowsData, props): OtelSpan[] => {
    const serviceData = workflowsData[props.serviceName ?? '']
    if (!serviceData || !props.spanID) return [] // Stable empty array reference
    // .filter creates new array, memoized by createSelector
    return serviceData.workflowSpans.filter((item) => item.parent_span_id === props.spanID)
  },
)

// Memoized selectAllSpanChildSpans (Recursive children - Using inline prop selector)
export const selectAllSpanChildSpans = createSelector(
  [
    selectWorkflowsData,
    (_state: RootState, props: { serviceName: string | undefined; spanID: string | undefined }) => props,
  ],
  (workflowsData, props): OtelSpan[] => {
    const { serviceName, spanID } = props
    if (!serviceName || !spanID) return [] // Stable empty array reference

    const allSpans = workflowsData[serviceName]?.workflowSpans
    if (!allSpans) return [] // Stable empty array reference

    // Find starting span without calling another selector directly inside result func
    const startingSpan = allSpans.find((item) => item.span_id === spanID)
    if (!startingSpan) return [] // Stable empty array reference

    // Logic to find children - this computation only runs if workflowsData or props change
    const children: OtelSpan[] = []
    const queue: OtelSpan[] = [startingSpan]
    const visited = new Set<string>() // Prevent cycles
    visited.add(startingSpan.span_id)

    while (queue.length > 0) {
      const currentSpan = queue.shift()!
      // .filter creates a new array, but it's okay inside the memoized function
      const childSpans = allSpans.filter((s) => s.parent_span_id === currentSpan.span_id)
      for (const child of childSpans) {
        if (!visited.has(child.span_id)) {
          children.push(child)
          queue.push(child)
          visited.add(child.span_id)
        }
      }
    }
    // The returned 'children' array reference is memoized by createSelector
    return children
  },
)

/**
 * Selector: Select First Child State Event Of A Given Span
 * This selector finds the first set_state event in the child spans of a given span
 * @returns {JunjoSetStateEvent | undefined}
 */
export const selectFirstStateEventInSpanOrChildren = createSelector(
  [selectWorkflowSpan, selectAllSpanChildSpans],
  (workflowSpan, childSpans): JunjoSetStateEvent | undefined => {
    // Extract all the state_events from the child spans
    const stateEvents: JunjoSetStateEvent[] = []

    const combinedSpans = [workflowSpan, ...childSpans]

    combinedSpans.forEach((span) => {
      if (!span) return // Skip if span is undefined

      // Basic check if events_json exists and is an array
      if (Array.isArray(span.events_json)) {
        span.events_json.forEach((event) => {
          // Assuming JunjoSetStateEventSchema.parse returns a newly parsed object
          const parsedEvent = JunjoSetStateEventSchema.safeParse(event)
          if (!parsedEvent.success) {
            console.error('Error parsing event in selector:', parsedEvent.error)
            return
          }
          stateEvents.push(parsedEvent.data)
        })
      }
    })

    // Sort the state events by their timeUnixNano in ascending order
    const sortedEvents = [...stateEvents].sort((a, b) => a.timeUnixNano - b.timeUnixNano)

    // Return the first event in the sorted array
    return sortedEvents[0]
  },
)

/**
 * Select all of a workflow's lineage spans
 * Recursively find all parent spans (lineage) of a given workflow span.
 * @returns {OtelSpan[]}
 */
export const selectWorkflowsLineageSpans = createSelector(
  [
    selectWorkflowsData,
    selectWorkflowSpan,
    (_state: RootState, props: { serviceName: string | undefined; spanID: string | undefined }) => props,
  ],
  (workflowsData, workflowSpan, props): OtelSpan[] => {
    const { serviceName, spanID } = props
    if (!serviceName || !spanID || !workflowSpan) return [] // Stable empty array reference

    const allLineageSpans = workflowsData[serviceName]?.workflowLineage
    if (!allLineageSpans) return [] // Stable empty array reference

    // Logic to find children - this computation only runs if workflowsData or props change
    const lineageSpans: OtelSpan[] = []

    // Recursively check the parent spans and add them to the lineageSpans
    function recursivelyBuildLineage(span: OtelSpan): OtelSpan | undefined {
      if (!allLineageSpans) return undefined // Stable empty array reference

      // Add to the beginning of the chain and continue traversing
      lineageSpans.unshift(span)

      // if not, get the parent span and recursively call this function to check it
      const parentSpan = allLineageSpans.find((s) => s.span_id === span.parent_span_id)
      if (parentSpan) {
        return recursivelyBuildLineage(parentSpan)
      }

      // If no parent span is found, break the recursion
      return undefined
    }
    // Start the recursion with the event span
    recursivelyBuildLineage(workflowSpan)

    return lineageSpans
  },
)

/**
 * Select All Workflow State Events
 * Memoized selectAllWorkflowStateEvents (Depends on memoized selectAllSpanChildSpans)
 * No direct prop selector needed here, as props are passed to selectAllSpanChildSpans implicitly
 * @returns {JunjoSetStateEvent[]} sorted by their timeUnixNano
 */
export const selectAllWorkflowStateEvents = createSelector(
  [selectWorkflowSpan, selectAllSpanChildSpans],
  (workflowSpan, childSpans): JunjoSetStateEvent[] => {
    const junjoSetStateEvents: JunjoSetStateEvent[] = []

    // Combine the workflow span and child spans
    const allSpans = [workflowSpan, ...childSpans].filter((span) => span !== undefined)

    allSpans.forEach((span) => {
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

/**
 * Select Spans with Exceptions
 * For a given workflow span, create a list of all of the workflow span's exceptions,
 * including its lineage and child spans.
 * @returns {OtelSpan[]} sorted by their timeUnixNano
 */
export const selectAllExceptionSpans = createSelector(
  [selectAllSpanChildSpans, selectWorkflowsLineageSpans],
  (childSpans, lineageSpans): OtelSpan[] => {
    const exceptionSpans: OtelSpan[] = []

    // combine the workflow span and child spans
    const allSpans = [...lineageSpans, ...childSpans].filter((span) => span !== undefined)
    if (!allSpans) return [] // Stable empty array reference

    for (const span of allSpans) {
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
 * Select: Span Has Exceptions
 */
export const selectSpanHasExceptions = createSelector([selectWorkflowSpan], (span): boolean => {
  if (!span) return false

  return span.events_json.some((event) => {
    return event.attributes && event.attributes['exception.type'] !== undefined
  })
})

/**
 * Workflow Execution Request Has Exceptions
 * Checks if the workflow span and its lineage spans or child spans have any exceptions.
 * Optimized to return early if any exceptions are found.
 * TODO: For performance, consider moving this to when the data is loaded.
 * @returns {boolean}
 */
export const workflowExecutionRequestHasExceptions = createSelector(
  [selectWorkflowsLineageSpans, selectAllSpanChildSpans],
  (lineageSpans, childSpans): boolean => {
    // 2) Check lineage spans
    for (const span of lineageSpans) {
      if (Array.isArray(span.events_json)) {
        for (const ev of span.events_json) {
          if (ev.attributes?.['exception.type'] !== undefined) {
            return true
          }
        }
      }
    }

    // 3) Check child spans
    for (const span of childSpans) {
      if (Array.isArray(span.events_json)) {
        for (const ev of span.events_json) {
          if (ev.attributes?.['exception.type'] !== undefined) {
            return true
          }
        }
      }
    }

    return false
  },
)

/**
 * Select Workflow Span By Store ID
 * Allows for the selection of a workflow span by its store ID
 */
export const selectWorkflowSpanByStoreID = createSelector(
  [
    selectWorkflowsData,
    (_state: RootState, props: { serviceName: string | undefined; storeID: string | undefined }) => props,
  ],
  (workflowsData, props): OtelSpan | undefined => {
    if (!props.storeID || !props.serviceName) return undefined

    const serviceData = workflowsData[props.serviceName ?? '']
    if (!serviceData) return undefined

    return serviceData.workflowSpans.find((span) => span.junjo_wf_store_id === props.storeID)
  },
)

/**
 * Select Active Span's Workflow Span
 * Allows for the selection of a workflow span from the active span.
 *
 * The input selectors select all spans umbrellad under the top-level workflow span.
 * The current span's workflow span may be a lower level subflow or a workflow span.
 *
 * If: the active span is a workflow span, return it
 * Else: Recursively check the parent spans to find the workflow span
 */
export const selectActiveSpansWorkflowSpan = createSelector(
  [selectWorkflowDetailActiveSpan, selectAllSpanChildSpans, selectWorkflowsLineageSpans],
  (activeSpan, childSpans, lineageSpans): OtelSpan | undefined => {
    if (!activeSpan) return undefined

    // combine the workflow span and child spans
    const allSpans = [...lineageSpans, ...childSpans].filter((span) => span !== undefined)
    // console.log(`Checking active span's workflow span...`)
    // console.log('Active Span: ', activeSpan)
    // console.log('All Spans: ', allSpans)

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
      console.warn('No workflow span found for active span:', activeSpan)
      return undefined
    }
    // Start the recursion with the event span
    return recursivelyCheckParentSpansForWorkflowSpan(activeSpan)
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
  [selectActiveSetStateEvent, selectWorkflowDetailActiveSpan, selectActiveSpansWorkflowSpan],
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
 * Select Set State Events by Store ID
 */
export const selectSetStateEventsByStoreID = createSelector(
  [
    selectWorkflowSpan,
    selectAllSpanChildSpans,
    (_state: RootState, props: { storeID: string | undefined }) => props,
  ],
  (workflowSpan, childSpans, { storeID }): JunjoSetStateEvent[] => {
    const junjoSetStateEvents: JunjoSetStateEvent[] = []
    if (!storeID) return junjoSetStateEvents

    // combine the workflow span and child spans
    const allSpans = [workflowSpan, ...childSpans].filter((span) => span !== undefined)

    allSpans.forEach((span) => {
      // Basic check if events_json exists and is an array
      if (Array.isArray(span.events_json)) {
        span.events_json.forEach((event) => {
          try {
            // Assuming JunjoSetStateEventSchema.parse returns a newly parsed object
            const parsedEvent = JunjoSetStateEventSchema.parse(event)
            if (parsedEvent.attributes['junjo.store.id'] === storeID) {
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
 * Select All Span State Events
 * @returns {JunjoSetStateEvent[]} sorted by their timeUnixNano
 */
export const selectStateEventsBySpanId = (
  state: RootState,
  props: { serviceName: string | undefined; spanId: string | undefined },
) => {
  const serviceData = state.otelState.workflows.data[props.serviceName ?? '']
  if (!serviceData || !props.spanId) return [] // Stable empty array reference
  const workflowSpans = serviceData.workflowSpans
  if (!workflowSpans) return [] // Stable empty array reference
  const span = workflowSpans.find((item) => item.span_id === props.spanId)
  if (!span) return [] // Stable empty array reference
  const junjoSetStateEvents: JunjoSetStateEvent[] = []
  if (Array.isArray(span.events_json)) {
    span.events_json.forEach((event) => {
      try {
        // Assuming JunjoSetStateEventSchema.parse returns a newly parsed object
        const parsedEvent = JunjoSetStateEventSchema.parse(event)
        junjoSetStateEvents.push(parsedEvent)
      } catch (error) {
        // Consider less noisy logging or specific handling
        // console.error('Error parsing event in selector:', error);
      }
    })
  }
  junjoSetStateEvents.sort((a, b) => a.timeUnixNano - b.timeUnixNano)
  return junjoSetStateEvents
}

/**
 * Select State Event Parent Span
 * @returns {OtelSpan | undefined}
 */
export const selectStateEventParentSpan = createSelector(
  [
    selectAllSpanChildSpans,
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
 * Identify Workflow Chain
 * Returns a chain of workflows and subflows that this span is part of.
 * Recursively checks the parent spans to find workflow / subflow spans
 * to identify the entire chain of subflows.
 *
 * @returns {OtelSpan | undefined}
 */
export const identifyWorkflowChainDEPRECATED = createWorkflowChainSelector(
  [
    // Input 1: All workflow data
    selectWorkflowsData,
    // Input 2: The current top-level workflow span
    selectWorkflowSpan,
    // Input 3: The active span
    selectWorkflowDetailActiveSpan,
  ],
  // Result function now receives individual values, not the props object
  (workflowsData, topLevelWorkflowSpan, activeSpan): OtelSpan[] => {
    if (!workflowsData || !topLevelWorkflowSpan) return []

    // Initial array
    const workflowSpanChain: OtelSpan[] = []

    // If we have an active span, we need to find the workflow chain
    if (activeSpan) {
      // Destructure the active span to get the service name and starting span ID
      const { service_name: serviceName, span_id: startingSpanId } = activeSpan

      // Get the service workflow data
      const serviceWorkflowData = workflowsData[serviceName]
      if (!serviceWorkflowData) return workflowSpanChain

      // Combine all spans for easier lookup *inside* the memoized function

      // TODO: for RenderJunjoGraphMermaid: This can operate off the new traces store
      const allSpans = [...serviceWorkflowData.workflowLineage, ...serviceWorkflowData.workflowSpans]

      // Find the actual starting span object using the stable ID *inside* the memoized function
      const actualStartingSpan = allSpans.find((s) => s.span_id === startingSpanId)

      if (!actualStartingSpan) {
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
        const parentSpan = allSpans.find((s) => s.span_id === span.parent_span_id)
        if (parentSpan) {
          return recursivelyBuildWorkflowSpanChain(parentSpan)
        }

        // If no parent span is found, break the recursion
        return undefined
      }
      // Start the recursion with the event span
      recursivelyBuildWorkflowSpanChain(actualStartingSpan)
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
 * Select: Before Span State Event In Workflow
 * This selector finds the last set_state event before the current span starts in the same workflow
 *
 * 1. Find all set_state events that operate on the same store ID (meaning, we know the workflow is the same)
 * 2. Find the last set_state event before the active span starts
 *
 * @returns {JunjoSetStateEvent | undefined}
 */
export const selectBeforeSpanStateEventInWorkflow = createSelector(
  [selectWorkflowDetailActiveSpan, selectSetStateEventsByStoreID],
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

export const selectPrevWorkflowSpanID = (
  state: RootState,
  props: { serviceName: string | undefined; spanID: string | undefined },
) => {
  const workflowSpans = selectServiceWorkflows(state, { serviceName: props.serviceName })
  if (!workflowSpans) return undefined

  const spanIndex = workflowSpans.findIndex((item) => item.span_id === props.spanID)
  if (spanIndex === -1 || spanIndex === 0) return undefined
  return workflowSpans[spanIndex - 1].span_id
}

export const selectNextWorkflowSpanID = (
  state: RootState,
  props: { serviceName: string | undefined; spanID: string | undefined },
) => {
  const workflowSpans = selectServiceWorkflows(state, { serviceName: props.serviceName })
  if (!workflowSpans) return undefined
  const spanIndex = workflowSpans.findIndex((item) => item.span_id === props.spanID)
  if (spanIndex === -1 || spanIndex === workflowSpans.length - 1) return undefined
  return workflowSpans[spanIndex + 1].span_id
}

/*********************** NEW RAW OTEL SELECTORS ************************/

/**
 * Select First Junjo Parent Span
 * Given a span, find the first parent span that is a Junjo span (not 'other').
 * This includes the starting span itself.
 * @returns {OtelSpan | undefined}
 */
export const selectFirstJunjoParentSpan = createSelector(
  [selectWorkflowDetailActiveSpan, selectAllSpanChildSpans, selectWorkflowsLineageSpans],
  (activeSpan, childSpans, lineageSpans): OtelSpan | undefined => {
    if (!activeSpan) return undefined

    // combine the workflow span and child spans
    const allSpans = [...lineageSpans, ...childSpans].filter((span) => span !== undefined)

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
