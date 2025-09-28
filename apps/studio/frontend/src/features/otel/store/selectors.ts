import { createSelector, createSelectorCreator, lruMemoize } from '@reduxjs/toolkit'
import { RootState } from '../../../root-store/store'
import { JunjoSetStateEvent, JunjoSetStateEventSchema, JunjoSpanType, OtelSpan } from '../schemas/schemas'

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

// /**
//  * Selector: Select First Child State Event Of A Given Span
//  * This selector finds the first set_state event in the child spans of a given span
//  * @returns {JunjoSetStateEvent | undefined}
//  */
// export const selectFirstStateEventInSpanOrChildren = createSelector(
//   [selectWorkflowSpan, selectSpanAndChildren],
//   (workflowSpan, childSpans): JunjoSetStateEvent | undefined => {
//     // Extract all the state_events from the child spans
//     const stateEvents: JunjoSetStateEvent[] = []

//     const combinedSpans = [workflowSpan, ...childSpans]

//     combinedSpans.forEach((span) => {
//       if (!span) return // Skip if span is undefined

//       // Basic check if events_json exists and is an array
//       if (Array.isArray(span.events_json)) {
//         span.events_json.forEach((event) => {
//           // Assuming JunjoSetStateEventSchema.parse returns a newly parsed object
//           const parsedEvent = JunjoSetStateEventSchema.safeParse(event)
//           if (!parsedEvent.success) {
//             console.error('Error parsing event in selector:', parsedEvent.error)
//             return
//           }
//           stateEvents.push(parsedEvent.data)
//         })
//       }
//     })

//     // Sort the state events by their timeUnixNano in ascending order
//     const sortedEvents = [...stateEvents].sort((a, b) => a.timeUnixNano - b.timeUnixNano)

//     // Return the first event in the sorted array
//     return sortedEvents[0]
//   },
// )

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
 * Select: Span Has Exceptions
 */
export const selectSpanHasExceptions = createSelector([selectWorkflowSpan], (span): boolean => {
  if (!span) return false

  return span.events_json.some((event) => {
    return event.attributes && event.attributes['exception.type'] !== undefined
  })
})

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
