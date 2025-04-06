import { createSelector } from '@reduxjs/toolkit'
import { RootState } from '../../../root-store/store'
import { NodeSetStateEvent, NodeSetStateEventSchema, OtelSpan } from './schemas'

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

// --- Memoized Selectors ---
export const selectServiceWorkflows = createSelector(
  [selectWorkflowsData, (_state: RootState, props: { serviceName: string | undefined }) => props],
  (workflowsData, props) => {
    const serviceData = workflowsData[props.serviceName ?? '']
    if (!serviceData) return [] // Return stable empty array reference

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
    // .find returns existing reference or undefined, which is fine.
    return serviceData.workflowSpans.find((item) => item.span_id === props.spanID)
  },
)

// Direct children only
export const selectSpanChildren = createSelector(
  [
    selectWorkflowsData,
    (_state: RootState, props: { serviceName: string | undefined; workflowSpanID: string | undefined }) =>
      props,
  ],
  (workflowsData, props): OtelSpan[] => {
    const serviceData = workflowsData[props.serviceName ?? '']
    if (!serviceData || !props.workflowSpanID) return [] // Stable empty array reference
    // .filter creates new array, memoized by createSelector
    return serviceData.workflowSpans.filter((item) => item.parent_span_id === props.workflowSpanID)
  },
)

// Memoized selectAllWorkflowChildSpans (Recursive children - Using inline prop selector)
export const selectAllWorkflowChildSpans = createSelector(
  [
    selectWorkflowsData,
    (_state: RootState, props: { serviceName: string | undefined; workflowSpanID: string | undefined }) =>
      props,
  ],
  (workflowsData, props): OtelSpan[] => {
    const { serviceName, workflowSpanID } = props
    if (!serviceName || !workflowSpanID) return [] // Stable empty array reference

    const allSpans = workflowsData[serviceName]?.workflowSpans
    if (!allSpans) return [] // Stable empty array reference

    // Find starting span without calling another selector directly inside result func
    const workflowSpan = allSpans.find((item) => item.span_id === workflowSpanID)
    if (!workflowSpan) return [] // Stable empty array reference

    // Logic to find children - this computation only runs if workflowsData or props change
    const children: OtelSpan[] = []
    const queue: OtelSpan[] = [workflowSpan]
    const visited = new Set<string>() // Prevent cycles
    visited.add(workflowSpan.span_id)

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
 * Select All Workflow State Events
 * Memoized selectAllWorkflowStateEvents (Depends on memoized selectAllWorkflowChildSpans)
 * No direct prop selector needed here, as props are passed to selectAllWorkflowChildSpans implicitly
 * @returns {NodeSetStateEvent[]} sorted by their timeUnixNano
 */
export const selectAllWorkflowStateEvents = createSelector(
  [selectAllWorkflowChildSpans],
  (childSpans): NodeSetStateEvent[] => {
    const nodeSetStateEvents: NodeSetStateEvent[] = []
    childSpans.forEach((span) => {
      // Basic check if events_json exists and is an array
      if (Array.isArray(span.events_json)) {
        span.events_json.forEach((event) => {
          try {
            // Assuming NodeSetStateEventSchema.parse returns a newly parsed object
            const parsedEvent = NodeSetStateEventSchema.parse(event)
            nodeSetStateEvents.push(parsedEvent)
          } catch (error) {
            // Consider less noisy logging or specific handling
            // console.error('Error parsing event in selector:', error);
          }
        })
      }
    })

    nodeSetStateEvents.sort((a, b) => a.timeUnixNano - b.timeUnixNano)
    // createSelector memoizes this returned reference
    return nodeSetStateEvents
  },
)

export const selectPrevWorkflowSpanID = (
  state: RootState,
  props: { serviceName: string | undefined; workflowSpanID: string | undefined },
) => {
  const workflowSpans = selectServiceWorkflows(state, { serviceName: props.serviceName })
  if (!workflowSpans) return undefined

  const spanIndex = workflowSpans.findIndex((item) => item.span_id === props.workflowSpanID)
  if (spanIndex === -1 || spanIndex === 0) return undefined
  return workflowSpans[spanIndex - 1].span_id
}

export const selectNextWorkflowSpanID = (
  state: RootState,
  props: { serviceName: string | undefined; workflowSpanID: string | undefined },
) => {
  const workflowSpans = selectServiceWorkflows(state, { serviceName: props.serviceName })
  if (!workflowSpans) return undefined
  const spanIndex = workflowSpans.findIndex((item) => item.span_id === props.workflowSpanID)
  if (spanIndex === -1 || spanIndex === workflowSpans.length - 1) return undefined
  return workflowSpans[spanIndex + 1].span_id
}
