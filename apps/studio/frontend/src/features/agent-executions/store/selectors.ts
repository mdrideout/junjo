import type { RootState } from '../../../root-store/store'
import type { AgentExecutionQuery } from '../schemas/query'
import { getAgentExecutionDetailKey, getAgentExecutionQueryKey } from '../schemas/query'
import type { AgentExecutionDetailRequestState, AgentExecutionListRequestState } from './slice'

const EMPTY_LIST_REQUEST: AgentExecutionListRequestState = {
  data: [],
  loading: false,
  error: null,
}

const EMPTY_DETAIL_REQUEST: AgentExecutionDetailRequestState = {
  data: null,
  loading: false,
  error: null,
}

export function selectAgentExecutionListRequest(
  state: RootState,
  query: AgentExecutionQuery,
): AgentExecutionListRequestState {
  return state.agentExecutionsState.lists[getAgentExecutionQueryKey(query)] ?? EMPTY_LIST_REQUEST
}

export function selectAgentExecutionDetailRequest(
  state: RootState,
  identity: { traceId: string; agentSpanId: string },
): AgentExecutionDetailRequestState {
  return (
    state.agentExecutionsState.details[getAgentExecutionDetailKey(identity.traceId, identity.agentSpanId)] ??
    EMPTY_DETAIL_REQUEST
  )
}
