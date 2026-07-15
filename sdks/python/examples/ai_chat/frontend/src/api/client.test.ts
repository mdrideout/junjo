import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  createTurn,
  createContact,
  getConversationTurns,
  getConversations,
  getPublicConfig,
  getTurn,
  normalizeApiBaseUrl,
  resolveApiAssetUrl,
  resolveApiUrl,
} from './client'

const turn = {
  object_type: 'ai_chat.turn',
  schema_version: 1,
  id: 'turn/1',
  revision: 3,
  conversation_id: 'conversation/1',
  sequence: 1,
  status: 'completed',
  context_policy: { id: 'recent-completed-turns', version: 1, recent_turn_limit: 8 },
  user_message: {
    id: 'user-1', turn_id: 'turn/1', role: 'user', content: 'Hello',
    image_url: null, image_alt: null, created_at: '2026-07-14T12:00:00.000Z',
  },
  assistant_message: {
    id: 'assistant-1', turn_id: 'turn/1', role: 'assistant', content: 'Hi',
    image_url: null, image_alt: null, created_at: '2026-07-14T12:00:01.000Z',
  },
  execution_references: { workflow_run_id: 'workflow-run-1', agent_run_id: 'agent-run-1' },
  failure: null,
  created_at: '2026-07-14T12:00:00.000Z',
  updated_at: '2026-07-14T12:00:02.000Z',
  completed_at: '2026-07-14T12:00:02.000Z',
}

const conversation = {
  id: 'conversation/1',
  title: 'Evidence chat',
  contact: {
    object_type: 'ai_chat.contact', schema_version: 1,
    id: 'contact-1', first_name: 'Junjo', last_name: 'Guide', sex: 'female',
    age: 31,
    personality: {
      openness: 0.8, conscientiousness: 0.6, extraversion: 0.7,
      agreeableness: 0.8, neuroticism: 0.2, intelligence: 0.8,
      religiousness: 0.1, attractiveness: 0.8, trauma: 0.2,
    },
    latitude: 40.6782, longitude: -73.9442,
    city: 'Brooklyn', state: 'NY', bio: 'A useful profile.',
    avatar_url: '/api/images/avatar.svg',
  },
  last_message_at: null,
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('chat API client', () => {
  it('normalizes one explicit API origin for requests and relative assets', () => {
    expect(normalizeApiBaseUrl(undefined)).toBe('')
    expect(normalizeApiBaseUrl('https://api.example.test/')).toBe('https://api.example.test')
    expect(resolveApiUrl('/api/images/one.svg', 'https://api.example.test')).toBe(
      'https://api.example.test/api/images/one.svg',
    )
    expect(resolveApiAssetUrl('https://assets.example.test/chart.png')).toBe(
      'https://assets.example.test/chart.png',
    )
    expect(() => normalizeApiBaseUrl('https://api.example.test/v1')).toThrow('HTTP origin')
    expect(() => resolveApiUrl('api/images/one.svg')).toThrow('root-relative')
    expect(() => resolveApiAssetUrl('/\\assets.example.test/one.svg')).toThrow('backslashes')
  })

  it('uses the exact config, conversation, and Turn read endpoints', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        debug_enabled: false,
        studio_ui_url: null,
        service_namespace: 'junjo.examples',
        service_name: 'ai-chat',
      }))
      .mockResolvedValueOnce(jsonResponse({
        conversations: [conversation],
      }))
      .mockResolvedValueOnce(jsonResponse({
        conversation_id: 'conversation/1',
        turns: [turn],
      }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getPublicConfig()).resolves.toMatchObject({ debug_enabled: false })
    await expect(getConversations()).resolves.toMatchObject({
      conversations: [{ id: 'conversation/1' }],
    })
    await expect(getConversationTurns('conversation/1')).resolves.toMatchObject({
      turns: [{ id: 'turn/1' }],
    })

    expect(fetchMock.mock.calls[0]?.[0]).toBe('http://localhost:26252/api/config')
    expect(fetchMock.mock.calls[1]?.[0]).toBe('http://localhost:26252/api/conversations')
    expect(fetchMock.mock.calls[2]?.[0]).toBe(
      'http://localhost:26252/api/conversations/conversation%2F1/turns',
    )
  })

  it('posts one strict server-owned Turn admission request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(turn))
    vi.stubGlobal('fetch', fetchMock)

    const result = await createTurn('conversation/1', { text: 'Hello' })

    expect(result.execution_references.workflow_run_id).toBe('workflow-run-1')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://localhost:26252/api/conversations/conversation%2F1/turns')
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"text":"Hello"}')
  })

  it('polls a Turn by server identity and creates contacts through strict endpoints', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(turn))
      .mockResolvedValueOnce(jsonResponse({ conversation }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getTurn('turn/1')).resolves.toMatchObject({ id: 'turn/1' })
    await expect(createContact({ sex: 'female' })).resolves.toEqual({ conversation })

    expect(fetchMock.mock.calls[0]?.[0]).toBe('http://localhost:26252/api/turns/turn%2F1')
    expect(fetchMock.mock.calls[1]?.[0]).toBe('http://localhost:26252/api/contacts')
  })

  it('preserves the failed persisted Turn and execution references', async () => {
    const failedTurn = {
      ...turn,
      revision: 2,
      status: 'failed',
      assistant_message: null,
      execution_references: { workflow_run_id: null, agent_run_id: 'failed-agent-run' },
      failure: {
        code: 'agent_execution_failed',
        detail: 'Agent execution failed.',
        termination_reason: 'tool_error',
      },
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      type: 'https://junjo.ai/problems/ai-chat/turn-execution-failed',
      title: 'Turn execution failed',
      status: 500,
      detail: 'Agent execution failed.',
      instance: '/api/conversations/conversation-1/turns',
      turn_id: 'turn/1',
      workflow_run_id: null,
      agent_run_id: 'failed-agent-run',
      termination_reason: 'tool_error',
      turn: failedTurn,
    }, 500)))

    const failure = await createTurn('conversation/1', { text: 'Draw' }).catch(
      (error: unknown) => error,
    )

    expect(failure).toBeInstanceOf(ApiError)
    expect(failure).toMatchObject({
      message: 'Agent execution failed.',
      status: 500,
      agentRunId: 'failed-agent-run',
      terminationReason: 'tool_error',
      turn: { id: 'turn/1', status: 'failed' },
    })
  })
})
