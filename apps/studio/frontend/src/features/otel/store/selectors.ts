import { RootState } from '../../../root-store/store'

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

export const selectWorkflowSpanChildren = (
  state: RootState,
  props: { serviceName: string | undefined; workflowSpanID: string | undefined },
) =>
  state.otelState.workflows.data[props.serviceName ?? '']?.workflowSpans.filter(
    (item) => item.parent_span_id === props.workflowSpanID,
  )

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
