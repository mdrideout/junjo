import { RootState } from '../../../../root-store/store'
import { OtelSpan } from '../../../traces/schemas/schemas'
import type { WorkflowSpanListState } from './slice'

type WorkflowSpanListRequest = Pick<WorkflowSpanListState, 'workflowSpanList' | 'loading' | 'error'>

const PENDING_WORKFLOW_SPAN_LIST: WorkflowSpanListRequest = {
  workflowSpanList: [],
  loading: true,
  error: null,
}

export function selectWorkflowSpanListRequest(
  state: RootState,
  serviceName: string,
): WorkflowSpanListRequest {
  const request = state.workflowSpanListState
  return request.listServiceName === serviceName ? request : PENDING_WORKFLOW_SPAN_LIST
}

function selectWorkflowSpansForService(state: RootState, serviceName: string | undefined): OtelSpan[] {
  if (!serviceName || state.workflowSpanListState.listServiceName !== serviceName) return []
  return state.workflowSpanListState.workflowSpanList
}

export const selectPrevWorkflowSpan = (
  state: RootState,
  props: { serviceName: string | undefined; spanID: string | undefined },
) => {
  const workflowSpans = selectWorkflowSpansForService(state, props.serviceName)
  const spanIndex = workflowSpans.findIndex((item) => item.span_id === props.spanID)
  if (spanIndex === -1 || spanIndex === 0) return undefined
  return workflowSpans[spanIndex - 1]
}

export const selectNextWorkflowSpan = (
  state: RootState,
  props: { serviceName: string | undefined; spanID: string | undefined },
) => {
  const workflowSpans = selectWorkflowSpansForService(state, props.serviceName)
  const spanIndex = workflowSpans.findIndex((item) => item.span_id === props.spanID)
  if (spanIndex === -1 || spanIndex === workflowSpans.length - 1) return undefined
  return workflowSpans[spanIndex + 1]
}
