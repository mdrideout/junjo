import { waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { API_BASE, server } from '../../../auth/test-utils/mock-server'
import { store, type RootState } from '../../../root-store/store'
import { getAgentExecutionDetailKey, getAgentExecutionQueryKey } from '../schemas/query'
import { makeAgentExecutionDetailFixture } from '../testing/fixtures'
import { selectAgentExecutionDetailRequest, selectAgentExecutionListRequest } from './selectors'
import {
  AgentExecutionsActions,
  agentExecutionsReducer,
  initialAgentExecutionsState,
} from './slice'

describe('Agent execution state', () => {
  it('owns request state independently by deterministic list and detail keys', () => {
    const fixture = makeAgentExecutionDetailFixture()
    const query = { service_namespace: 'junjo.examples', service_name: 'ai-chat' }
    const listKey = getAgentExecutionQueryKey(query)
    const detailKey = getAgentExecutionDetailKey(
      fixture.summary.trace_id,
      fixture.summary.agent_span_id,
    )

    let state = agentExecutionsReducer(
      initialAgentExecutionsState,
      AgentExecutionsActions.setListLoading({ key: listKey, loading: true }),
    )
    state = agentExecutionsReducer(
      state,
      AgentExecutionsActions.setListData({ key: listKey, data: [fixture.summary] }),
    )
    state = agentExecutionsReducer(
      state,
      AgentExecutionsActions.setDetailData({ key: detailKey, data: fixture }),
    )

    const root = { agentExecutionsState: state } as RootState
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
    const root = { agentExecutionsState: initialAgentExecutionsState } as RootState

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

  it('listener middleware records a semantic detail request failure', async () => {
    const traceId = '22222222222222222222222222222222'
    const agentSpanId = 'eeeeeeeeeeeeeeee'
    server.use(
      http.get(
        `${API_BASE}/api/v1/agent-executions/:trace_id/:agent_span_id`,
        () => new HttpResponse(null, { status: 500 }),
      ),
    )

    store.dispatch(AgentExecutionsActions.fetchAgentExecutionDetail({ traceId, agentSpanId }))

    await waitFor(() => {
      expect(
        selectAgentExecutionDetailRequest(store.getState(), { traceId, agentSpanId }),
      ).toEqual({
        data: null,
        loading: false,
        error: 'Failed to fetch Agent execution (500)',
      })
    })
  })
})
