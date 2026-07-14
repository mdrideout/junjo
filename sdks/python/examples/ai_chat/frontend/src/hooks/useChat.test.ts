import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  createTurn,
  getConversationMessages,
  getConversations,
} from '../api/client'
import { useChat } from './useChat'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    createTurn: vi.fn(),
    getConversationMessages: vi.fn(),
    getConversations: vi.fn(),
  }
})

const initialMessage = {
  id: 'user-message-1',
  turn_id: 'turn-1',
  role: 'user' as const,
  content: 'Original content',
  image_url: null,
  image_alt: null,
  created_at: '2026-07-14T12:00:00.000Z',
}

const completedTurn = {
  conversation_id: 'conversation-1',
  workflow_run_id: 'workflow-run-1',
  agent_run_id: 'agent-run-1',
  user_message: {
    ...initialMessage,
    content: 'Validated server content',
  },
  assistant_message: {
    id: 'assistant-message-1',
    turn_id: 'turn-1',
    role: 'assistant' as const,
    content: 'Validated assistant response',
    image_url: null,
    image_alt: null,
    created_at: '2026-07-14T12:00:01.000Z',
  },
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getConversations).mockResolvedValue({
    conversations: [{ id: 'conversation-1', title: 'Evidence chat' }],
  })
  vi.mocked(getConversationMessages).mockResolvedValue({
    conversation_id: 'conversation-1',
    messages: [initialMessage],
  })
})

async function renderLoadedChat() {
  const hook = renderHook(() => useChat())
  await waitFor(() => {
    expect(hook.result.current.loadingMessages).toBe(false)
    expect(hook.result.current.messages).toHaveLength(1)
  })
  return hook
}

describe('useChat', () => {
  it('directly upserts both POST-returned messages and evidence without refetching', async () => {
    vi.mocked(createTurn).mockResolvedValue(completedTurn)
    const hook = await renderLoadedChat()

    let succeeded = false
    await act(async () => {
      succeeded = await hook.result.current.sendTurn('  Hello  ')
    })

    expect(succeeded).toBe(true)
    expect(createTurn).toHaveBeenCalledWith('conversation-1', { text: 'Hello' })
    expect(getConversationMessages).toHaveBeenCalledTimes(1)
    expect(hook.result.current.messages).toHaveLength(2)
    expect(hook.result.current.messages[0]?.content).toBe('Validated server content')
    expect(hook.result.current.evidenceByTurnId['turn-1']).toEqual({
      workflowRunId: 'workflow-run-1',
      agentRunId: 'agent-run-1',
    })
  })

  it('preserves the server response order when returned timestamps are equal', async () => {
    const timestamp = '2026-07-14T12:00:01.000Z'
    vi.mocked(createTurn).mockResolvedValue({
      ...completedTurn,
      user_message: {
        ...completedTurn.user_message,
        id: 'z-user-message-2',
        turn_id: 'turn-2',
        created_at: timestamp,
      },
      assistant_message: {
        ...completedTurn.assistant_message,
        id: 'a-assistant-message-2',
        turn_id: 'turn-2',
        created_at: timestamp,
      },
    })
    const hook = await renderLoadedChat()

    await act(async () => {
      await hook.result.current.sendTurn('Hello')
    })

    expect(hook.result.current.messages.slice(-2).map((message) => message.id)).toEqual([
      'z-user-message-2',
      'a-assistant-message-2',
    ])
    expect(hook.result.current.messages.slice(-2).map((message) => message.role)).toEqual([
      'user',
      'assistant',
    ])
  })

  it('allows only one synchronous turn request at a time', async () => {
    let finishTurn: (turn: typeof completedTurn) => void = () => undefined
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
    expect(createTurn).toHaveBeenCalledWith('conversation-1', { text: 'First' })
  })

  it('keeps the selected conversation fixed until its turn completes', async () => {
    vi.mocked(getConversations).mockResolvedValue({
      conversations: [
        { id: 'conversation-1', title: 'Evidence chat' },
        { id: 'conversation-2', title: 'Another chat' },
      ],
    })
    let finishTurn: (turn: typeof completedTurn) => void = () => undefined
    vi.mocked(createTurn).mockReturnValue(new Promise((resolve) => {
      finishTurn = resolve
    }))
    const hook = await renderLoadedChat()

    let request = Promise.resolve(false)
    act(() => {
      request = hook.result.current.sendTurn('Stay here')
      hook.result.current.selectConversation('conversation-2')
    })

    expect(hook.result.current.selectedConversationId).toBe('conversation-1')
    expect(getConversationMessages).toHaveBeenCalledTimes(1)

    await act(async () => {
      finishTurn(completedTurn)
      await request
    })

    expect(hook.result.current.selectedConversationId).toBe('conversation-1')
    expect(
      hook.result.current.messages[hook.result.current.messages.length - 1]?.content,
    ).toBe(
      'Validated assistant response',
    )
    expect(getConversationMessages).toHaveBeenCalledTimes(1)
  })

  it('preserves loaded messages and reports a synchronous turn error', async () => {
    vi.mocked(createTurn).mockRejectedValue(new Error('Agent execution failed.'))
    const hook = await renderLoadedChat()

    let succeeded = true
    await act(async () => {
      succeeded = await hook.result.current.sendTurn('Hello')
    })

    expect(succeeded).toBe(false)
    expect(hook.result.current.messages).toEqual([initialMessage])
    expect(hook.result.current.evidenceByTurnId).toEqual({})
    expect(hook.result.current.error).toEqual({
      message: 'Agent execution failed.',
      agentRunId: null,
      terminationReason: null,
    })
    expect(getConversationMessages).toHaveBeenCalledTimes(1)
  })

  it('keeps failed Agent identity and terminal reason visible', async () => {
    vi.mocked(createTurn).mockRejectedValue(new ApiError(
      500,
      'Image rendering failed.',
      'failed-agent-run',
      'tool_error',
    ))
    const hook = await renderLoadedChat()

    await act(async () => {
      await hook.result.current.sendTurn('Draw')
    })

    expect(hook.result.current.error).toEqual({
      message: 'Image rendering failed.',
      agentRunId: 'failed-agent-run',
      terminationReason: 'tool_error',
    })
  })
})
