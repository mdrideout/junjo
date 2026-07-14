import { waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { API_BASE, server } from '../../../auth/test-utils/mock-server'
import { store, type RootState } from '../../../root-store/store'
import { getAgentExecutionQueryKey } from '../schemas/query'
import { makeAgentExecutionDetailFixture } from '../testing/fixtures'
import { selectAgentExecutionDetailRequest, selectAgentExecutionListRequest } from './selectors'
import {
  AgentExecutionsActions,
  agentExecutionsReducer,
  initialAgentExecutionsState,
} from './slice'
import type { TraceEvidence } from '../../traces/schemas/trace-evidence'

function evidenceForDetail(detail: ReturnType<typeof makeAgentExecutionDetailFixture>): TraceEvidence {
  const storeId = detail.state.store_id
  if (storeId === null) throw new Error('Expected admitted Agent fixture Store')
  return {
    trace_id: detail.summary.trace_id,
    spans: [],
    executables_by_span_id: {
      [detail.summary.agent_span_id]: {
        executable_type: 'agent',
        owner_span_id: detail.summary.agent_span_id,
        runtime_id: detail.summary.runtime_id,
        store_id: storeId,
        unavailable_store: null,
        summary: detail.summary,
        definition: detail.definition,
        input: detail.input,
        output: detail.output,
        input_candidate: detail.input_candidate,
        history_candidate: detail.history_candidate,
        error: detail.error,
        cancellation: detail.cancellation,
        integrity: detail.integrity,
      },
    },
    operations_by_owner_runtime_id: {
      [detail.summary.runtime_id]: Object.fromEntries(
        detail.operations.map((operation) => [operation.span_id, operation]),
      ),
    },
    stores_by_id: {
      [storeId]: {
        store_id: storeId,
        owner_span_id: detail.summary.agent_span_id,
        owner_runtime_id: detail.summary.runtime_id,
        owner_executable_type: 'agent',
        detail: detail.state,
        integrity: detail.integrity,
      },
    },
    relationships_by_owner_span_id: {
      [detail.summary.agent_span_id]: {
        parent: detail.parent_executable,
        nested: detail.nested_executables,
      },
    },
    diagnostics: [],
  }
}

describe('Agent execution state', () => {
  it('keeps list request state separate while deriving detail from trace evidence', () => {
    const fixture = makeAgentExecutionDetailFixture()
    const query = { service_namespace: 'junjo.examples', service_name: 'ai-chat' }
    const listKey = getAgentExecutionQueryKey(query)
    let state = agentExecutionsReducer(
      initialAgentExecutionsState,
      AgentExecutionsActions.setListLoading({ key: listKey, loading: true }),
    )
    state = agentExecutionsReducer(
      state,
      AgentExecutionsActions.setListData({ key: listKey, data: [fixture.summary] }),
    )
    const base = store.getState()
    const root = {
      ...base,
      agentExecutionsState: state,
      tracesState: {
        ...base.tracesState,
        traceEvidence: {
          [fixture.summary.trace_id]: evidenceForDetail(fixture),
        },
      },
    } satisfies RootState
    expect(selectAgentExecutionListRequest(root, query)).toMatchObject({
      loading: true,
      data: [fixture.summary],
    })
    expect(
      selectAgentExecutionDetailRequest(root, {
        traceId: fixture.summary.trace_id,
        agentSpanId: fixture.summary.agent_span_id,
      }).data,
    ).toEqual(fixture)
  })

  it('returns immutable empty selector results for requests that have not started', () => {
    const root = {
      ...store.getState(),
      agentExecutionsState: initialAgentExecutionsState,
    } satisfies RootState

    expect(
      selectAgentExecutionListRequest(root, {
        service_namespace: '',
        service_name: 'not-requested',
      }),
    ).toEqual({ data: [], loading: false, error: null })
    expect(
      selectAgentExecutionDetailRequest(root, {
        traceId: '33333333333333333333333333333333',
        agentSpanId: 'ffffffffffffffff',
      }),
    ).toEqual({ data: null, loading: false, error: null })
  })

  it('listener middleware deduplicates an in-flight list and stores parsed data', async () => {
    const fixture = makeAgentExecutionDetailFixture()
    const query = { service_namespace: 'junjo.examples', service_name: 'listener-ai-chat' }
    let requestCount = 0
    server.use(
      http.get(`${API_BASE}/api/v1/agent-executions`, () => {
        requestCount += 1
        return HttpResponse.json([fixture.summary])
      }),
    )

    store.dispatch(AgentExecutionsActions.fetchAgentExecutions(query))
    store.dispatch(AgentExecutionsActions.fetchAgentExecutions(query))

    await waitFor(() => {
      expect(selectAgentExecutionListRequest(store.getState(), query)).toMatchObject({
        loading: false,
        error: null,
        data: [fixture.summary],
      })
    })
    expect(requestCount).toBe(1)
  })

})
