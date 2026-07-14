import { createSelector } from '@reduxjs/toolkit'
import type { RootState } from '../../../root-store/store'
import type { AgentExecutionDetail } from '../schemas/agent-execution'
import type { AgentExecutionQuery } from '../schemas/query'
import { getAgentExecutionQueryKey } from '../schemas/query'
import type { AgentExecutionDetailRequestState, AgentExecutionListRequestState } from './slice'

const EMPTY_LIST_REQUEST: AgentExecutionListRequestState = {
  data: [],
  loading: false,
  error: null,
}

export function selectAgentExecutionListRequest(
  state: RootState,
  query: AgentExecutionQuery,
): AgentExecutionListRequestState {
  return state.agentExecutionsState.lists[getAgentExecutionQueryKey(query)] ?? EMPTY_LIST_REQUEST
}

export const selectAgentExecutionDetailRequest = createSelector(
  [
    (state: RootState) => state.tracesState.traceEvidence,
    (state: RootState) => state.tracesState.loading,
    (state: RootState) => state.tracesState.error,
    (_state: RootState, identity: { traceId: string; agentSpanId: string }) => identity,
  ],
  (evidenceByTraceId, loading, hasError, identity): AgentExecutionDetailRequestState => {
    const evidence = evidenceByTraceId[identity.traceId]
    const executable = evidence?.executables_by_span_id[identity.agentSpanId]
    if (executable?.executable_type !== 'agent') {
      return {
        data: null,
        loading,
        error: hasError ? 'Failed to fetch Agent execution' : null,
      }
    }

    const state = executable.store_id === null
      ? executable.unavailable_store
      : evidence.stores_by_id[executable.store_id]?.detail
    if (state === null || state === undefined) {
      return {
        data: null,
        loading: false,
        error: 'Agent Store evidence is unavailable',
      }
    }

    const relationships = evidence.relationships_by_owner_span_id[identity.agentSpanId]
    const operations = Object.values(
      evidence.operations_by_owner_runtime_id[executable.runtime_id] ?? {},
    ).sort((left, right) => left.sequence - right.sequence || left.span_id.localeCompare(right.span_id))
    const data: AgentExecutionDetail = {
      summary: executable.summary,
      definition: executable.definition,
      input: executable.input,
      output: executable.output,
      input_candidate: executable.input_candidate,
      history_candidate: executable.history_candidate,
      operations,
      state,
      parent_executable: relationships?.parent ?? null,
      nested_executables: relationships?.nested ?? [],
      error: executable.error,
      cancellation: executable.cancellation,
      integrity: executable.integrity,
    }
    return { data, loading: false, error: null }
  },
)
