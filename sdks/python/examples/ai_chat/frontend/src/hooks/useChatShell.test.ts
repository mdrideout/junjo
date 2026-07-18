import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createContact, getConversations, getPublicConfig } from '../api/client'
import { useChatShell } from './useChatShell'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    createContact: vi.fn(),
    getConversations: vi.fn(),
    getPublicConfig: vi.fn(),
  }
})

const conversation = {
  id: 'conversation-1',
  title: 'Evidence chat',
  contact: {
    object_type: 'ai_chat.contact' as const,
    schema_version: 1 as const,
    id: 'contact-1',
    first_name: 'Junjo',
    last_name: 'Guide',
    sex: 'female' as const,
    age: 31,
    personality: {
      openness: 0.8,
      conscientiousness: 0.6,
      extraversion: 0.7,
      agreeableness: 0.8,
      neuroticism: 0.2,
      intelligence: 0.8,
      religiousness: 0.1,
      attractiveness: 0.8,
      trauma: 0.2,
    },
    latitude: 40.6782,
    longitude: -73.9442,
    city: 'Brooklyn',
    state: 'NY',
    bio: 'A useful profile.',
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
  vi.mocked(getConversations).mockResolvedValue({ conversations: [conversation] })
})

describe('useChatShell', () => {
  it('owns global configuration and conversation summaries', async () => {
    const interval = vi.spyOn(window, 'setInterval')
    const hook = renderHook(() => useChatShell())

    await waitFor(() => expect(hook.result.current.loading).toBe(false))

    expect(hook.result.current.config?.service_name).toBe('ai-chat')
    expect(hook.result.current.conversations).toEqual([conversation])
    expect(interval.mock.calls.filter((call) => call[1] === 10000)).toHaveLength(1)

    hook.unmount()
    interval.mockRestore()
  })

  it('adds a created contact without owning route selection', async () => {
    const created = {
      ...conversation,
      id: 'conversation-2',
      contact: { ...conversation.contact, id: 'contact-2', first_name: 'Maya' },
    }
    vi.mocked(createContact).mockResolvedValue({ conversation: created })
    const hook = renderHook(() => useChatShell())
    await waitFor(() => expect(hook.result.current.loading).toBe(false))

    let result = null
    await act(async () => {
      result = await hook.result.current.createContact('female')
    })

    expect(result).toEqual(created)
    expect(hook.result.current.conversations[0]).toEqual(created)
  })
})
