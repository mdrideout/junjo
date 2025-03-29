import { createSelector } from '@reduxjs/toolkit'
import { RootState } from '../../../root-store/store'
import { NodeSetStateEvent, NodeSetStateEventSchema, OtelSpan } from './schemas'

// Selectors - Service Names
export const selectServiceNamesLoading = (state: RootState) => state.otelState.serviceNames.loading
export const selectServiceNamesError = (state: RootState) => state.otelState.serviceNames.error
export const selectServiceNames = (state: RootState) => state.otelState.serviceNames.data

// Selectors - Workflows
export const selectWorkflowsLoading = (state: RootState) => state.otelState.workflows.loading
export const selectWorkflowsError = (state: RootState) => state.otelState.workflows.error
export const selectServiceWorkflows = (state: RootState, props: { serviceName: string | undefined }) =>
  state.otelState.workflows.data[props.serviceName ?? '']?.workflowSpans.filter(
    (item) => item.junjo_span_type === 'workflow',
  )
export const selectWorkflowSpan = (
  state: RootState,
  props: { serviceName: string | undefined; spanID: string | undefined },
) =>
  state.otelState.workflows.data[props.serviceName ?? '']?.workflowSpans.find((item) => item.span_id === props.spanID)

export const selectSpanChildren = (
  state: RootState,
  props: { serviceName: string | undefined; workflowSpanID: string | undefined },
) =>
  state.otelState.workflows.data[props.serviceName ?? '']?.workflowSpans.filter(
    (item) => item.parent_span_id === props.workflowSpanID,
  )

export const selectAllWorkflowChildSpans = (
  state: RootState,
  props: { serviceName: string | undefined; workflowSpanID: string | undefined },
) => {
  const { serviceName, workflowSpanID } = props
  if (!serviceName || !workflowSpanID) return []

  const workflowSpan = selectWorkflowSpan(state, { serviceName, spanID: workflowSpanID })
  if (!workflowSpan) return []

  const allSpans = state.otelState.workflows.data[serviceName]?.workflowSpans
  if (!allSpans) return []

  const children = []
  const queue = [workflowSpan]
  while (queue.length > 0) {
    const currentSpan = queue.shift()!
    const childSpans = allSpans.filter((s) => s.parent_span_id === currentSpan.span_id)
    children.push(...childSpans)
    queue.push(...childSpans)
  }
  return children
}

/**
 * Select All Workflow State Events
 * @returns {NodeSetStateEvent[]} sorted by their timeUnixNano
 */
export const selectAllWorkflowStateEvents = (
  state: RootState,
  props: { serviceName: string | undefined; workflowSpanID: string | undefined },
) => {
  const childSpans = selectAllWorkflowChildSpans(state, props)

  // Get the set state events from the spans
  const nodeSetStateEvents: NodeSetStateEvent[] = []
  childSpans.forEach((span) => {
    span.events_json.forEach((event) => {
      try {
        const parsedEvent = NodeSetStateEventSchema.parse(event)
        nodeSetStateEvents.push(parsedEvent)
      } catch (error) {
        console.error('Error parsing event:', error)
      }
    })
  })

  // Sort the events by the order they occurred
  nodeSetStateEvents.sort((a, b) => a.timeUnixNano - b.timeUnixNano)

  return nodeSetStateEvents
}

export const selectPrevWorkflowSpanID = (
  state: RootState,
  props: { serviceName: string | undefined; workflowSpanID: string | undefined },
) => {
  const workflowSpans = selectServiceWorkflows(state, { serviceName: props.serviceName })
  if (!workflowSpans) return undefined

  console.log('Workflow Spans: ', workflowSpans)

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
