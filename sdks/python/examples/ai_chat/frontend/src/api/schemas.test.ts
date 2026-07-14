import { describe, expect, it } from 'vitest'
import {
  AgentErrorResponseSchema,
  ConversationsResponseSchema,
  CreateTurnRequestSchema,
  MAX_TURN_TEXT_LENGTH,
  MessagesResponseSchema,
  TurnResponseSchema,
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

describe('chat API schemas', () => {
  it('accepts only the exact Agent failure evidence envelope', () => {
    const failure = {
      detail: 'Tool execution failed.',
      agent_run_id: 'agent-run-1',
      termination_reason: 'tool_error',
    }
    expect(AgentErrorResponseSchema.parse(failure)).toEqual(failure)
    expect(() => AgentErrorResponseSchema.parse({ ...failure, legacy: true })).toThrow()
  })

  it('accepts the exact conversation and message response contracts', () => {
    expect(ConversationsResponseSchema.parse({
      conversations: [{ id: 'conversation-1', title: 'Example chat' }],
    }).conversations).toHaveLength(1)

    expect(MessagesResponseSchema.parse({
      conversation_id: 'conversation-1',
      messages: [userMessage, assistantMessage],
    }).messages).toHaveLength(2)
  })

  it('rejects extra fields and invalid timestamps', () => {
    expect(() => ConversationsResponseSchema.parse({
      conversations: [{ id: 'conversation-1', title: 'Chat', legacy: true }],
    })).toThrow()
    expect(() => MessagesResponseSchema.parse({
      conversation_id: 'conversation-1',
      messages: [{ ...userMessage, created_at: 'yesterday' }],
    })).toThrow()
  })

  it('requires accessible alt text for every image and no orphaned alt text', () => {
    expect(MessagesResponseSchema.parse({
      conversation_id: 'conversation-1',
      messages: [{
        ...assistantMessage,
        image_url: 'https://example.test/chart.png',
        image_alt: 'A chart of the conversation result',
      }],
    }).messages[0]?.image_alt).toBe('A chart of the conversation result')
    expect(() => MessagesResponseSchema.parse({
      conversation_id: 'conversation-1',
      messages: [{
        ...assistantMessage,
        image_url: 'https://example.test/chart.png',
        image_alt: null,
      }],
    })).toThrow()
    expect(() => MessagesResponseSchema.parse({
      conversation_id: 'conversation-1',
      messages: [{
        ...assistantMessage,
        image_url: null,
        image_alt: 'Orphaned alt text',
      }],
    })).toThrow()
  })

  it('requires the POST messages to have truthful roles and one turn identity', () => {
    const base = {
      conversation_id: 'conversation-1',
      workflow_run_id: 'workflow-run-1',
      agent_run_id: 'agent-run-1',
      user_message: userMessage,
      assistant_message: assistantMessage,
    }
    expect(TurnResponseSchema.parse(base).agent_run_id).toBe('agent-run-1')
    expect(() => TurnResponseSchema.parse({
      ...base,
      assistant_message: { ...assistantMessage, role: 'user' },
    })).toThrow()
    expect(() => TurnResponseSchema.parse({
      ...base,
      assistant_message: { ...assistantMessage, turn_id: 'turn-2' },
    })).toThrow()
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
