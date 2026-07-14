import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  createTurn,
  getConversationMessages,
  getConversations,
  normalizeApiBaseUrl,
  resolveApiAssetUrl,
  resolveApiUrl,
} from './client'

const message = (role: 'user' | 'assistant', id: string) => ({
  id,
  turn_id: 'turn/1',
  role,
  content: `${role} content`,
  image_url: null,
  image_alt: null,
  created_at: role === 'user'
    ? '2026-07-14T12:00:00.000Z'
    : '2026-07-14T12:00:01.000Z',
})

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

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
    expect(resolveApiAssetUrl('/api/images/one.svg', 'https://api.example.test')).toBe(
      'https://api.example.test/api/images/one.svg',
    )
    expect(() => normalizeApiBaseUrl('https://api.example.test/v1')).toThrow('HTTP origin')
    expect(() => resolveApiUrl('api/images/one.svg')).toThrow('root-relative')
    expect(() => resolveApiAssetUrl('//assets.example.test/one.svg')).toThrow('root-relative')
    expect(() => resolveApiAssetUrl('/\\assets.example.test/one.svg')).toThrow('backslashes')
    expect(() => resolveApiAssetUrl('/\nassets.example.test/one.svg')).toThrow('control')
    expect(() => resolveApiAssetUrl('images/one.svg')).toThrow('root-relative')
    expect(() => resolveApiAssetUrl('https://user:secret@assets.example.test/one.svg')).toThrow(
      'credentials',
    )
  })

  it('uses the exact read endpoints and validates their envelopes', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({
        conversations: [{ id: 'conversation/1', title: 'Evidence chat' }],
      }))
      .mockResolvedValueOnce(jsonResponse({
        conversation_id: 'conversation/1',
        messages: [message('user', 'user-1')],
      }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getConversations()).resolves.toMatchObject({
      conversations: [{ id: 'conversation/1' }],
    })
    await expect(getConversationMessages('conversation/1')).resolves.toMatchObject({
      conversation_id: 'conversation/1',
    })

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/conversations')
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/conversations/conversation%2F1/messages')
  })

  it('posts one strict synchronous turn request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      conversation_id: 'conversation/1',
      workflow_run_id: 'workflow-run-1',
      agent_run_id: 'agent-run-1',
      user_message: message('user', 'user-1'),
      assistant_message: message('assistant', 'assistant-1'),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await createTurn('conversation/1', { text: 'Hello' })

    expect(result.workflow_run_id).toBe('workflow-run-1')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/conversations/conversation%2F1/turns')
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"text":"Hello"}')
  })

  it('rejects a response whose conversation identity does not match the request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      conversation_id: 'different-conversation',
      messages: [],
    })))

    await expect(getConversationMessages('conversation-1')).rejects.toThrow(
      'different conversation',
    )
  })

  it('preserves strict failed Agent execution evidence', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      detail: 'Image rendering failed.',
      agent_run_id: 'failed-agent-run',
      termination_reason: 'tool_error',
    }, 500)))

    const failure = await createTurn('conversation-1', { text: 'Draw' }).catch(
      (error: unknown) => error,
    )

    expect(failure).toBeInstanceOf(ApiError)
    expect(failure).toMatchObject({
      message: 'Image rendering failed.',
      status: 500,
      agentRunId: 'failed-agent-run',
      terminationReason: 'tool_error',
    })
  })
})
