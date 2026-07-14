import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Conversation, Turn } from '../api/schemas'
import ChatReceiveImageBubble from './bubbles/ChatReceiveImageBubble'
import ChatSidebar from './sidebar/ChatSidebar'

const conversation: Conversation = {
  id: 'conversation-1',
  title: 'Maya Rivera',
  contact: {
    object_type: 'ai_chat.contact',
    schema_version: 1,
    id: 'contact-1',
    first_name: 'Maya',
    last_name: 'Rivera',
    sex: 'female',
    age: 30,
    personality: {
      openness: 0.8, conscientiousness: 0.6, extraversion: 0.7,
      agreeableness: 0.8, neuroticism: 0.2, intelligence: 0.8,
      religiousness: 0.1, attractiveness: 0.8, trauma: 0.2,
    },
    latitude: 40.6782,
    longitude: -73.9442,
    city: 'Brooklyn',
    state: 'NY',
    bio: 'Curious and warm.',
    avatar_url: '/api/images/avatar.svg',
  },
  last_message_at: null,
}

const imageTurn: Turn = {
  object_type: 'ai_chat.turn',
  schema_version: 1,
  id: 'turn-1',
  revision: 3,
  conversation_id: conversation.id,
  sequence: 1,
  status: 'completed',
  context_policy: { id: 'recent-completed-turns', version: 1, recent_turn_limit: 8 },
  user_message: {
    id: 'user-1', turn_id: 'turn-1', role: 'user', content: 'Draw this',
    image_url: null, image_alt: null, created_at: '2026-07-14T12:00:00.000Z',
  },
  assistant_message: {
    id: 'assistant-1', turn_id: 'turn-1', role: 'assistant', content: 'Here it is',
    image_url: '/api/images/result.svg', image_alt: 'A generated scene',
    created_at: '2026-07-14T12:00:01.000Z',
  },
  execution_references: { workflow_run_id: 'workflow-1', agent_run_id: null },
  failure: null,
  created_at: '2026-07-14T12:00:00.000Z',
  updated_at: '2026-07-14T12:00:02.000Z',
  completed_at: '2026-07-14T12:00:02.000Z',
}

afterEach(cleanup)

describe('restored AI Chat surface', () => {
  it('keeps contact creation, avatar profile, and unread interactions', async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined)
    render(
      <ChatSidebar
        conversations={[conversation]}
        activeChatId={undefined}
        loading={false}
        creatingContact={false}
        lastReadAtByChatId={{}}
        onSelect={vi.fn()}
        onCreateContact={onCreate}
      />,
    )
    const user = userEvent.setup()

    expect(screen.getByRole('button', { name: /New Male/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /New Female/ })).toBeInTheDocument()
    expect(screen.getByText('Maya Rivera')).toBeInTheDocument()
    await user.click(screen.getByText('View Profile'))
    expect(screen.getByText('Curious and warm.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /New Female/ }))
    expect(onCreate).toHaveBeenCalledWith('female')
  })

  it('keeps generated images zoomable without exposing debug UI by default', async () => {
    const message = imageTurn.assistant_message
    if (message === null) throw new Error('fixture requires an assistant message')
    render(<ChatReceiveImageBubble message={message} turn={imageTurn} config={null} />)
    const user = userEvent.setup()

    expect(screen.queryByText('Turn diagnostics')).not.toBeInTheDocument()
    await user.click(screen.getByRole('img', { name: 'A generated scene' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getAllByRole('img', { name: 'A generated scene' })).toHaveLength(2)
  })
})
