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
