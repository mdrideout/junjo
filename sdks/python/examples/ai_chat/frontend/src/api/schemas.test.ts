import { describe, expect, it } from 'vitest'
import {
  ConversationsResponseSchema,
  CreateTurnRequestSchema,
  MAX_TURN_TEXT_LENGTH,
  PublicConfigResponseSchema,
  TurnProblemResponseSchema,
  TurnSchema,
} from './schemas'

const userMessage = {
  id: 'message-user-1',
  turn_id: 'turn-1',
  role: 'user' as const,
  content: 'Hello',
  image_url: null,
  image_alt: null,
  created_at: '2026-07-14T12:00:00.000Z',
}

const assistantMessage = {
  id: 'message-assistant-1',
  turn_id: 'turn-1',
  role: 'assistant' as const,
  content: 'Hi there',
  image_url: null,
  image_alt: null,
  created_at: '2026-07-14T12:00:01.000Z',
}

const completedTurn = {
  object_type: 'ai_chat.turn' as const,
  schema_version: 1 as const,
  id: 'turn-1',
  revision: 3,
  conversation_id: 'conversation-1',
  sequence: 1,
  status: 'completed' as const,
  context_policy: {
    id: 'recent-completed-turns' as const,
    version: 1 as const,
    recent_turn_limit: 8,
  },
  user_message: userMessage,
  assistant_message: assistantMessage,
  execution_references: {
    workflow_run_id: 'workflow-run-1',
    agent_run_id: 'agent-run-1',
  },
  failure: null,
  created_at: '2026-07-14T12:00:00.000Z',
  updated_at: '2026-07-14T12:00:02.000Z',
  completed_at: '2026-07-14T12:00:02.000Z',
}

describe('chat API schemas', () => {
  it('accepts exact conversation, debug, and completed Turn contracts', () => {
    expect(ConversationsResponseSchema.parse({
      conversations: [{
        id: 'conversation-1',
        title: 'Example chat',
        contact: {
          object_type: 'ai_chat.contact' as const,
          schema_version: 1 as const,
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
      }],
    }).conversations).toHaveLength(1)
    expect(PublicConfigResponseSchema.parse({
      debug_enabled: true,
      studio_ui_url: 'http://localhost:26153',
      service_namespace: 'junjo.examples',
      service_name: 'ai-chat',
    }).debug_enabled).toBe(true)
    expect(TurnSchema.parse(completedTurn).execution_references.agent_run_id).toBe('agent-run-1')
  })

  it('rejects incoherent Turn lifecycle and message identities', () => {
    expect(() => TurnSchema.parse({ ...completedTurn, completed_at: null })).toThrow()
    expect(() => TurnSchema.parse({ ...completedTurn, assistant_message: null })).toThrow()
    expect(() => TurnSchema.parse({
      ...completedTurn,
      assistant_message: { ...assistantMessage, turn_id: 'different-turn' },
    })).toThrow()
    expect(() => TurnSchema.parse({ ...completedTurn, legacy: true })).toThrow()
  })

  it('requires accessible alt text for every image', () => {
    expect(() => TurnSchema.parse({
      ...completedTurn,
      assistant_message: {
        ...assistantMessage,
        image_url: 'https://example.test/chart.png',
        image_alt: null,
      },
    })).toThrow()
  })

  it('accepts a failed persisted Turn inside the strict problem contract', () => {
    const failedTurn = {
      ...completedTurn,
      revision: 2,
      status: 'failed' as const,
      assistant_message: null,
      execution_references: {
        workflow_run_id: null,
        agent_run_id: 'failed-agent-run',
      },
      failure: {
        code: 'agent_execution_failed',
        detail: 'Agent execution failed.',
        termination_reason: 'tool_error',
      },
    }
    const problem = TurnProblemResponseSchema.parse({
      type: 'https://junjo.ai/problems/ai-chat/turn-execution-failed',
      title: 'Turn execution failed',
      status: 500,
      detail: 'Agent execution failed.',
      instance: '/api/conversations/conversation-1/turns',
      turn_id: 'turn-1',
      workflow_run_id: null,
      agent_run_id: 'failed-agent-run',
      termination_reason: 'tool_error',
      turn: failedTurn,
    })
    expect(problem.turn?.status).toBe('failed')
  })

  it('matches the backend turn-text limit exactly', () => {
    expect(CreateTurnRequestSchema.parse({
      text: 'a'.repeat(MAX_TURN_TEXT_LENGTH),
    }).text).toHaveLength(MAX_TURN_TEXT_LENGTH)
    expect(() => CreateTurnRequestSchema.parse({
      text: 'a'.repeat(MAX_TURN_TEXT_LENGTH + 1),
    })).toThrow()
  })
})
