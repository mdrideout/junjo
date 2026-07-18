import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createTurn, getConversationTurns, getTurn } from '../api/client'
import type { Turn } from '../api/schemas'
import { useConversationTurns } from './useConversationTurns'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    createTurn: vi.fn(),
    getConversationTurns: vi.fn(),
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
    id: 'user-message-1',
    turn_id: 'turn-1',
    role: 'user',
    content: 'Validated server content',
    image_url: null,
    image_alt: null,
    created_at: '2026-07-14T12:00:00.000Z',
  },
  assistant_message: {
    id: 'assistant-message-1',
    turn_id: 'turn-1',
    role: 'assistant',
    content: 'Validated assistant response',
    image_url: null,
    image_alt: null,
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

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getConversationTurns).mockResolvedValue({
    conversation_id: 'conversation-1',
    turns: [],
  })
})

afterEach(() => {
  vi.useRealTimers()
})

async function renderLoadedConversation() {
  const hook = renderHook(() => useConversationTurns('conversation-1'))
  await waitFor(() => expect(hook.result.current.loading).toBe(false))
  return hook
}

describe('useConversationTurns', () => {
  it('loads only the requested conversation history', async () => {
    vi.mocked(getConversationTurns).mockResolvedValue({
      conversation_id: 'conversation-1',
      turns: [completedTurn],
    })

    const hook = await renderLoadedConversation()

    expect(getConversationTurns).toHaveBeenCalledWith('conversation-1', expect.any(AbortSignal))
    expect(hook.result.current.turns).toEqual([completedTurn])
  })

  it('admits a Turn and lets the pane-owned effect poll it to completion', async () => {
    vi.mocked(createTurn).mockResolvedValue(admittedTurn)
    vi.mocked(getTurn).mockResolvedValue(completedTurn)
    const hook = await renderLoadedConversation()
    vi.useFakeTimers()

    let succeeded = false
    await act(async () => {
      succeeded = await hook.result.current.sendTurn('  Hello  ')
    })

    expect(succeeded).toBe(true)
    expect(createTurn).toHaveBeenCalledWith('conversation-1', { text: 'Hello' })
    expect(hook.result.current.turns).toEqual([admittedTurn])
    expect(hook.result.current.sending).toBe(true)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    expect(getTurn).toHaveBeenCalledWith('turn-1', expect.any(AbortSignal))
    expect(hook.result.current.turns).toEqual([completedTurn])
    expect(hook.result.current.sending).toBe(false)
  })

  it('resumes polling when authoritative history contains an active Turn', async () => {
    vi.mocked(getConversationTurns).mockResolvedValue({
      conversation_id: 'conversation-1',
      turns: [admittedTurn],
    })
    vi.mocked(getTurn).mockResolvedValue(completedTurn)
    vi.useFakeTimers()
    const hook = renderHook(() => useConversationTurns('conversation-1'))

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(hook.result.current.turns).toEqual([admittedTurn])

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    expect(hook.result.current.turns).toEqual([completedTurn])
  })

  it('aborts an outstanding history load when the pane unmounts', async () => {
    let historySignal: AbortSignal | undefined
    let finishHistory: (value: { conversation_id: string; turns: Turn[] }) => void = () => undefined
    vi.mocked(getConversationTurns).mockImplementation((_conversationId, signal) => {
      historySignal = signal
      return new Promise((resolve) => {
        finishHistory = resolve
      })
    })

    const hook = renderHook(() => useConversationTurns('conversation-1'))
    expect(historySignal).toBeDefined()
    expect(historySignal?.aborted).toBe(false)

    hook.unmount()
    expect(historySignal?.aborted).toBe(true)

    await act(async () => {
      finishHistory({ conversation_id: 'conversation-1', turns: [completedTurn] })
      await Promise.resolve()
    })
  })

  it('aborts active Turn polling when the pane unmounts', async () => {
    let pollSignal: AbortSignal | undefined
    let finishPoll: (turn: Turn) => void = () => undefined
    vi.mocked(getConversationTurns).mockResolvedValue({
      conversation_id: 'conversation-1',
      turns: [admittedTurn],
    })
    vi.mocked(getTurn).mockImplementation((_turnId, signal) => {
      pollSignal = signal
      return new Promise((resolve) => {
        finishPoll = resolve
      })
    })
    vi.useFakeTimers()
    const hook = renderHook(() => useConversationTurns('conversation-1'))

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(hook.result.current.turns).toEqual([admittedTurn])

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    expect(pollSignal).toBeDefined()
    expect(pollSignal?.aborted).toBe(false)
    hook.unmount()
    expect(pollSignal?.aborted).toBe(true)

    await act(async () => {
      finishPoll(completedTurn)
      await Promise.resolve()
    })
  })

  it('derives durable failure presentation from loaded Turn state', async () => {
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
    vi.mocked(getConversationTurns).mockResolvedValue({
      conversation_id: 'conversation-1',
      turns: [failedTurn],
    })
    const hook = await renderLoadedConversation()

    expect(hook.result.current.error).toEqual({
      message: 'Agent execution failed.',
      workflowRunId: null,
      agentRunId: 'failed-agent-run',
      terminationReason: 'tool_error',
    })
  })

  it('does not admit a second Turn in the same active conversation', async () => {
    vi.mocked(getConversationTurns).mockResolvedValue({
      conversation_id: 'conversation-1',
      turns: [admittedTurn],
    })
    const hook = await renderLoadedConversation()

    let succeeded = true
    await act(async () => {
      succeeded = await hook.result.current.sendTurn('Second')
    })

    expect(succeeded).toBe(false)
    expect(createTurn).not.toHaveBeenCalled()
  })
})
