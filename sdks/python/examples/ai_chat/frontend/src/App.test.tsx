import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import {
  createContact,
  createTurn,
  getConversationTurns,
  getConversations,
  getPublicConfig,
  getTurn,
} from './api/client'
import type { Conversation, Turn } from './api/schemas'

vi.mock('./api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/client')>()
  return {
    ...actual,
    createContact: vi.fn(),
    createTurn: vi.fn(),
    getConversationTurns: vi.fn(),
    getConversations: vi.fn(),
    getPublicConfig: vi.fn(),
    getTurn: vi.fn(),
  }
})

function conversation(id: string, firstName: string): Conversation {
  return {
    id,
    title: `${firstName} chat`,
    contact: {
      object_type: 'ai_chat.contact',
      schema_version: 1,
      id: `contact-${id}`,
      first_name: firstName,
      last_name: 'Person',
      sex: 'female',
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
      bio: `${firstName} profile`,
      avatar_url: '/api/images/avatar.svg',
    },
    last_message_at: null,
  }
}

function turn(conversationId: string, status: 'admitted' | 'completed'): Turn {
  const completed = status === 'completed'
  return {
    object_type: 'ai_chat.turn',
    schema_version: 1,
    id: `turn-${conversationId}`,
    revision: completed ? 2 : 0,
    conversation_id: conversationId,
    sequence: 1,
    status,
    context_policy: { id: 'recent-completed-turns', version: 1, recent_turn_limit: 8 },
    user_message: {
      id: `user-${conversationId}`,
      turn_id: `turn-${conversationId}`,
      role: 'user',
      content: `Question ${conversationId}`,
      image_url: null,
      image_alt: null,
      created_at: '2026-07-14T12:00:00.000Z',
    },
    assistant_message: completed
      ? {
          id: `assistant-${conversationId}`,
          turn_id: `turn-${conversationId}`,
          role: 'assistant',
          content: `Answer ${conversationId}`,
          image_url: null,
          image_alt: null,
          created_at: '2026-07-14T12:00:01.000Z',
        }
      : null,
    execution_references: {
      workflow_run_id: completed ? `workflow-${conversationId}` : null,
      agent_run_id: completed ? `agent-${conversationId}` : null,
    },
    failure: null,
    created_at: '2026-07-14T12:00:00.000Z',
    updated_at: completed ? '2026-07-14T12:00:02.000Z' : '2026-07-14T12:00:00.000Z',
    completed_at: completed ? '2026-07-14T12:00:02.000Z' : null,
  }
}

const alpha = conversation('alpha', 'Alpha')
const beta = conversation('beta', 'Beta')
const charlie = conversation('charlie', 'Charlie')

function LocationProbe() {
  return <div data-testid="location">{useLocation().pathname}</div>
}

function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/:chat_id?"
          element={
            <>
              <App />
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  vi.mocked(getPublicConfig).mockResolvedValue({
    debug_enabled: false,
    studio_ui_url: null,
    service_namespace: 'junjo.examples',
    service_name: 'ai-chat',
  })
  vi.mocked(getConversations).mockResolvedValue({ conversations: [alpha, beta] })
  vi.mocked(getConversationTurns).mockImplementation(async (conversationId) => ({
    conversation_id: conversationId,
    turns: conversationId === 'alpha' ? [turn('alpha', 'admitted')] : [],
  }))
  vi.mocked(getTurn).mockImplementation(() => new Promise(() => undefined))
})

describe('App conversation ownership', () => {
  it('creates and uses another conversation while the original Turn continues', async () => {
    vi.mocked(createContact).mockResolvedValue({ conversation: charlie })
    vi.mocked(createTurn).mockImplementation(async (conversationId) => turn(conversationId, 'admitted'))
    renderApp('/alpha')

    expect(await screen.findByText('Question alpha')).toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /New Female/ }))

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/charlie'))
    expect(screen.getByText('Charlie chat')).toBeInTheDocument()
    expect(screen.queryByText('Question alpha')).not.toBeInTheDocument()

    await user.type(screen.getByRole('textbox', { name: 'Message' }), 'Hello Charlie')
    await user.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(createTurn).toHaveBeenCalledWith('charlie', { text: 'Hello Charlie' })
    })
    expect(screen.getByText('Question charlie')).toBeInTheDocument()
  })

  it('returns to authoritative history after navigating away from an active Turn', async () => {
    let alphaLoads = 0
    vi.mocked(getConversationTurns).mockImplementation(async (conversationId) => {
      if (conversationId !== 'alpha') return { conversation_id: conversationId, turns: [] }
      alphaLoads += 1
      return {
        conversation_id: conversationId,
        turns: [turn('alpha', alphaLoads === 1 ? 'admitted' : 'completed')],
      }
    })
    renderApp('/alpha')

    expect(await screen.findByText('Question alpha')).toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Beta Person/ }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/beta'))
    expect(screen.queryByText('Question alpha')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Alpha Person/ }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/alpha'))
    expect(await screen.findByText('Answer alpha')).toBeInTheDocument()
  })

  it('resets the composer when the route selects a different conversation key', async () => {
    vi.mocked(getConversationTurns).mockImplementation(async (conversationId) => ({
      conversation_id: conversationId,
      turns: [],
    }))
    renderApp('/alpha')

    const composer = await screen.findByRole('textbox', { name: 'Message' })
    const user = userEvent.setup()
    await user.type(composer, 'Draft for Alpha')
    expect(composer).toHaveValue('Draft for Alpha')

    await user.click(screen.getByRole('button', { name: /Beta Person/ }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/beta'))
    expect(screen.getByRole('textbox', { name: 'Message' })).toHaveValue('')
  })
})
