import { describe, expect, it } from 'vitest'

import { AgentExecutionQuerySchema } from './query'

describe('Agent execution query', () => {
  it('requires aware ordered time bounds before issuing a request', () => {
    expect(AgentExecutionQuerySchema.safeParse({
      service_namespace: '',
      service_name: 'ai-chat',
      start_time: '2026-07-14T00:00:00',
    }).success).toBe(false)
    expect(AgentExecutionQuerySchema.safeParse({
      service_namespace: '',
      service_name: 'ai-chat',
      start_time: '2026-07-15T00:00:00Z',
      end_time: '2026-07-14T00:00:00Z',
    }).success).toBe(false)
    expect(AgentExecutionQuerySchema.safeParse({
      service_namespace: '',
      service_name: 'ai-chat',
      start_time: '2026-07-14T00:00:00Z',
      end_time: '2026-07-14T00:00:00Z',
    }).success).toBe(true)
  })
})
