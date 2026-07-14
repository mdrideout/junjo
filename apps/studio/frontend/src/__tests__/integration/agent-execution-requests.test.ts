import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { API_BASE, server } from '../../auth/test-utils/mock-server'
import { getAgentExecution } from '../../features/agent-executions/fetch/get-agent-execution'
import { listAgentExecutions } from '../../features/agent-executions/fetch/list-agent-executions'
import { makeAgentExecutionDetailFixture } from '../../features/agent-executions/testing/fixtures'

describe('Agent semantic API requests', () => {
  it('sends the explicit service scope and supported list filters', async () => {
    const fixture = makeAgentExecutionDetailFixture()
    let requestUrl: URL | null = null
    let credentials: RequestCredentials | null = null

    server.use(
      http.get(`${API_BASE}/api/v1/agent-executions`, ({ request }) => {
        requestUrl = new URL(request.url)
        credentials = request.credentials
        return HttpResponse.json([fixture.summary])
      }),
    )

    const result = await listAgentExecutions({
      service_namespace: '',
      service_name: 'ai-chat',
      agent_key: 'chat-agent',
      structural_id: fixture.summary.structural_id,
      service_version: '0.1.0',
      outcome: 'completed',
      start_time: '2026-07-14T00:00:00.000Z',
      end_time: '2026-07-15T00:00:00.000Z',
      limit: 25,
    })

    expect(result).toEqual([fixture.summary])
    expect(credentials).toBe('include')
    expect(requestUrl).not.toBeNull()
    const parameters = requestUrl!.searchParams
    expect(parameters.get('service_namespace')).toBe('')
    expect(parameters.get('service_name')).toBe('ai-chat')
    expect(parameters.get('agent_key')).toBe('chat-agent')
    expect(parameters.get('structural_id')).toBe(fixture.summary.structural_id)
    expect(parameters.get('service_version')).toBe('0.1.0')
    expect(parameters.get('outcome')).toBe('completed')
    expect(parameters.get('start_time')).toBe('2026-07-14T00:00:00.000Z')
    expect(parameters.get('end_time')).toBe('2026-07-15T00:00:00.000Z')
    expect(parameters.get('limit')).toBe('25')
  })

  it('requests one execution by canonical trace and Agent span identity', async () => {
    const fixture = makeAgentExecutionDetailFixture()
    let observedPath = ''

    server.use(
      http.get(`${API_BASE}/api/v1/agent-executions/:trace_id/:agent_span_id`, ({ request }) => {
        observedPath = new URL(request.url).pathname
        return HttpResponse.json(fixture)
      }),
    )

    const result = await getAgentExecution(fixture.summary.trace_id, fixture.summary.agent_span_id)

    expect(observedPath).toBe(
      '/api/v1/agent-executions/11111111111111111111111111111111/aaaaaaaaaaaaaaaa',
    )
    expect(result.summary.runtime_id).toBe('agent_run_01JFIXTURE')
  })

  it('rejects invalid identities before issuing a request', async () => {
    await expect(getAgentExecution('not-a-trace-id', 'not-a-span-id')).rejects.toThrow(
      'Trace ID must be 32 lowercase hexadecimal characters',
    )
  })

  it('rejects non-semantic or malformed responses instead of interpreting transport data', async () => {
    server.use(
      http.get(`${API_BASE}/api/v1/agent-executions`, () =>
        HttpResponse.json([{ trace_id: '11111111111111111111111111111111', spans: [] }]),
      ),
    )

    await expect(
      listAgentExecutions({ service_namespace: '', service_name: 'ai-chat' }),
    ).rejects.toThrow()
  })

  it('surfaces list and detail HTTP failures with endpoint-specific messages', async () => {
    const fixture = makeAgentExecutionDetailFixture()
    server.use(
      http.get(`${API_BASE}/api/v1/agent-executions`, () => new HttpResponse(null, { status: 503 })),
      http.get(
        `${API_BASE}/api/v1/agent-executions/:trace_id/:agent_span_id`,
        () => new HttpResponse(null, { status: 404 }),
      ),
    )

    await expect(
      listAgentExecutions({ service_namespace: '', service_name: 'ai-chat' }),
    ).rejects.toThrow('Failed to fetch Agent executions (503)')
    await expect(
      getAgentExecution(fixture.summary.trace_id, fixture.summary.agent_span_id),
    ).rejects.toThrow('Failed to fetch Agent execution (404)')
  })

  it('preserves typed backend evidence rejection diagnostics', async () => {
    const fixture = makeAgentExecutionDetailFixture()
    server.use(
      http.get(
        `${API_BASE}/api/v1/agent-executions/:trace_id/:agent_span_id`,
        () => HttpResponse.json(
          {
            code: 'unsupported_contract',
            message: 'Telemetry contract 1 is not supported.',
            diagnostics: [
              {
                code: 'unsupported_contract_version',
                path: 'resource.contract_version',
                message: 'Expected contract version 2.',
              },
            ],
          },
          { status: 409 },
        ),
      ),
    )

    await expect(
      getAgentExecution(fixture.summary.trace_id, fixture.summary.agent_span_id),
    ).rejects.toThrow(
      'unsupported_contract: Telemetry contract 1 is not supported. — unsupported_contract_version at resource.contract_version',
    )
  })

  it('keeps request-validation 422 separate from stored-evidence conflicts', async () => {
    server.use(
      http.get(`${API_BASE}/api/v1/agent-executions`, () => HttpResponse.json(
        {
          detail: [
            {
              type: 'timezone_aware',
              loc: ['query', 'start_time'],
              msg: 'Input should have timezone info',
              input: '2026-07-14T00:00:00',
            },
          ],
        },
        { status: 422 },
      )),
    )

    await expect(
      listAgentExecutions({ service_namespace: '', service_name: 'ai-chat' }),
    ).rejects.toThrow('Failed to fetch Agent executions (422)')
  })
})
