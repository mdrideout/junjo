import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiError,
  createTurn,
  getConversationMessages,
  getConversations,
} from '../api/client'
import type {
  Conversation,
  Message,
  TurnEvidence,
} from '../api/schemas'

export interface ChatFailure {
  message: string
  agentRunId: string | null
  terminationReason: string | null
}

function failureFrom(error: unknown): ChatFailure {
  return {
    message: error instanceof Error ? error.message : 'The chat request failed.',
    agentRunId: error instanceof ApiError ? error.agentRunId : null,
    terminationReason: error instanceof ApiError ? error.terminationReason : null,
  }
}

function upsertMessages(current: Message[], received: Message[]): Message[] {
  const receivedIds = new Set(received.map((message) => message.id))
  return [
    ...current.filter((message) => !receivedIds.has(message.id)),
    ...received,
  ]
}

export interface ChatState {
  conversations: Conversation[]
  selectedConversationId: string | null
  messages: Message[]
  evidenceByTurnId: Record<string, TurnEvidence>
  loadingConversations: boolean
  loadingMessages: boolean
  sending: boolean
  error: ChatFailure | null
  selectConversation: (conversationId: string) => void
  sendTurn: (text: string) => Promise<boolean>
}

export function useChat(): ChatState {
  const turnInFlight = useRef(false)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [evidenceByTurnId, setEvidenceByTurnId] = useState<Record<string, TurnEvidence>>({})
  const [loadingConversations, setLoadingConversations] = useState(true)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<ChatFailure | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void getConversations(controller.signal)
      .then(({ conversations: received }) => {
        setConversations(received)
        setSelectedConversationId(received[0]?.id ?? null)
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(failureFrom(reason))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingConversations(false)
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    setMessages([])
    setEvidenceByTurnId({})
    if (selectedConversationId === null) {
      setLoadingMessages(false)
      return
    }

    const controller = new AbortController()
    setLoadingMessages(true)
    setError(null)
    void getConversationMessages(selectedConversationId, controller.signal)
      .then(({ messages: received }) => setMessages(received))
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(failureFrom(reason))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingMessages(false)
      })
    return () => controller.abort()
  }, [selectedConversationId])

  const selectConversation = useCallback((conversationId: string) => {
    if (turnInFlight.current) return
    setSelectedConversationId(conversationId)
  }, [])

  const sendTurn = useCallback(async (text: string): Promise<boolean> => {
    if (selectedConversationId === null || turnInFlight.current) return false
    const normalized = text.trim()
    if (!normalized) return false

    turnInFlight.current = true
    setSending(true)
    setError(null)
    try {
      const turn = await createTurn(selectedConversationId, { text: normalized })
      setMessages((current) => upsertMessages(
        current,
        [turn.user_message, turn.assistant_message],
      ))
      setEvidenceByTurnId((current) => ({
        ...current,
        [turn.assistant_message.turn_id]: {
          workflowRunId: turn.workflow_run_id,
          agentRunId: turn.agent_run_id,
        },
      }))
      return true
    } catch (reason: unknown) {
      setError(failureFrom(reason))
      return false
    } finally {
      turnInFlight.current = false
      setSending(false)
    }
  }, [selectedConversationId])

  return {
    conversations,
    selectedConversationId,
    messages,
    evidenceByTurnId,
    loadingConversations,
    loadingMessages,
    sending,
    error,
    selectConversation,
    sendTurn,
  }
}
