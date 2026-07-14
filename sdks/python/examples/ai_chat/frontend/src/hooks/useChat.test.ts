import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createTurn,
  createContact,
  getConversationTurns,
  getConversations,
  getPublicConfig,
  getTurn,
} from '../api/client'
import type { Turn } from '../api/schemas'
import { useChat } from './useChat'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    createTurn: vi.fn(),
    createContact: vi.fn(),
    getConversationTurns: vi.fn(),
    getConversations: vi.fn(),
    getPublicConfig: vi.fn(),
    getTurn: vi.fn(),
  }
})

const completedTurn: Turn = {
  object_type: 'ai_chat.turn',
  schema_version: 1,
  id: 'turn-1',
  revision: 3,
  conversation_id: 'conversation-1',
  sequence: 1,
  status: 'completed',
  context_policy: { id: 'recent-completed-turns', version: 1, recent_turn_limit: 8 },
  user_message: {
    id: 'user-message-1', turn_id: 'turn-1', role: 'user', content: 'Validated server content',
    image_url: null, image_alt: null, created_at: '2026-07-14T12:00:00.000Z',
  },
  assistant_message: {
    id: 'assistant-message-1', turn_id: 'turn-1', role: 'assistant',
    content: 'Validated assistant response', image_url: null, image_alt: null,
    created_at: '2026-07-14T12:00:01.000Z',
  },
  execution_references: { workflow_run_id: 'workflow-run-1', agent_run_id: 'agent-run-1' },
  failure: null,
  created_at: '2026-07-14T12:00:00.000Z',
  updated_at: '2026-07-14T12:00:02.000Z',
  completed_at: '2026-07-14T12:00:02.000Z',
}

const admittedTurn: Turn = {
  ...completedTurn,
  revision: 0,
  status: 'admitted',
  assistant_message: null,
  execution_references: { workflow_run_id: null, agent_run_id: null },
  completed_at: null,
}

const conversation = {
  id: 'conversation-1',
  title: 'Evidence chat',
  contact: {
    object_type: 'ai_chat.contact' as const, schema_version: 1 as const,
    id: 'contact-1', first_name: 'Junjo', last_name: 'Guide', sex: 'female' as const,
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

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getPublicConfig).mockResolvedValue({
    debug_enabled: true,
    studio_ui_url: 'http://localhost:26153',
    service_namespace: 'junjo.examples',
    service_name: 'ai-chat',
  })
  vi.mocked(getConversations).mockResolvedValue({
    conversations: [conversation],
  })
  vi.mocked(getConversationTurns).mockResolvedValue({
    conversation_id: 'conversation-1',
    turns: [],
  })
})

async function renderLoadedChat() {
  const hook = renderHook(() => useChat())
  await waitFor(() => {
    expect(hook.result.current.loadingTurns).toBe(false)
    expect(hook.result.current.selectedConversationId).toBe('conversation-1')
  })
  return hook
}

describe('useChat', () => {
  it('shows the admitted Turn and polls its server identity to completion', async () => {
    vi.mocked(createTurn).mockResolvedValue(admittedTurn)
    vi.mocked(getTurn).mockResolvedValue(completedTurn)
    const hook = await renderLoadedChat()

    let succeeded = false
    await act(async () => {
      succeeded = await hook.result.current.sendTurn('  Hello  ')
    })

    expect(succeeded).toBe(true)
    expect(createTurn).toHaveBeenCalledWith('conversation-1', { text: 'Hello' })
    expect(getTurn).toHaveBeenCalledWith('turn-1')
    expect(getConversationTurns).toHaveBeenCalledTimes(1)
    expect(hook.result.current.turns).toEqual([completedTurn])
    expect(hook.result.current.config?.debug_enabled).toBe(true)
  })

  it('allows only one active Turn request at a time', async () => {
    let finishTurn: (turn: Turn) => void = () => undefined
    vi.mocked(createTurn).mockReturnValue(new Promise((resolve) => {
      finishTurn = resolve
    }))
    const hook = await renderLoadedChat()

    let firstRequest: Promise<boolean> | undefined
    let secondSucceeded = true
    await act(async () => {
      firstRequest = hook.result.current.sendTurn('First')
      secondSucceeded = await hook.result.current.sendTurn('Second')
      finishTurn(completedTurn)
      await firstRequest
    })

    expect(secondSucceeded).toBe(false)
    expect(createTurn).toHaveBeenCalledTimes(1)
  })

  it('upserts a failed polled Turn and retains diagnostic identities', async () => {
    const failedTurn: Turn = {
      ...completedTurn,
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
    vi.mocked(createTurn).mockResolvedValue(admittedTurn)
    vi.mocked(getTurn).mockResolvedValue(failedTurn)
    const hook = await renderLoadedChat()

    await act(async () => {
      await hook.result.current.sendTurn('Draw')
    })

    expect(hook.result.current.turns).toEqual([failedTurn])
    expect(hook.result.current.error).toEqual({
      message: 'Agent execution failed.',
      workflowRunId: null,
      agentRunId: 'failed-agent-run',
      terminationReason: 'tool_error',
    })
  })

  it('adds a newly created contact conversation and selects it', async () => {
    const created = {
      ...conversation,
      id: 'conversation-2',
      contact: { ...conversation.contact, id: 'contact-2', first_name: 'Maya' },
    }
    vi.mocked(createContact).mockResolvedValue({ conversation: created })
    const hook = await renderLoadedChat()

    let result = null
    await act(async () => {
      result = await hook.result.current.createContact('female')
    })

    expect(result).toEqual(created)
    expect(hook.result.current.selectedConversationId).toBe('conversation-2')
    expect(hook.result.current.conversations[0]).toEqual(created)
  })
})
