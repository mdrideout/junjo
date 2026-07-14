import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiError,
  createContact as createContactRequest,
  createTurn,
  getConversationTurns,
  getConversations,
  getPublicConfig,
  getTurn,
} from '../api/client'
import type { ContactSex, Conversation, PublicConfig, Turn } from '../api/schemas'

export interface ChatFailure {
  message: string
  workflowRunId: string | null
  agentRunId: string | null
  terminationReason: string | null
}

function failureFrom(error: unknown): ChatFailure {
  return {
    message: error instanceof Error ? error.message : 'The chat request failed.',
    workflowRunId: error instanceof ApiError ? error.workflowRunId : null,
    agentRunId: error instanceof ApiError ? error.agentRunId : null,
    terminationReason: error instanceof ApiError ? error.terminationReason : null,
  }
}

function upsertTurn(current: Turn[], received: Turn): Turn[] {
  return [...current.filter((turn) => turn.id !== received.id), received]
    .sort((left, right) => left.sequence - right.sequence)
}

const TERMINAL_STATUSES = new Set<Turn['status']>(['completed', 'failed', 'cancelled'])

async function waitForTerminalTurn(initial: Turn): Promise<Turn> {
  let current = initial
  for (let attempt = 0; attempt < 120 && !TERMINAL_STATUSES.has(current.status); attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 250))
    current = await getTurn(current.id)
  }
  if (!TERMINAL_STATUSES.has(current.status)) {
    throw new Error('Turn execution did not finish before the local polling deadline.')
  }
  return current
}

export interface ChatState {
  config: PublicConfig | null
  conversations: Conversation[]
  selectedConversationId: string | null
  turns: Turn[]
  loadingConversations: boolean
  loadingTurns: boolean
  sending: boolean
  creatingContact: boolean
  error: ChatFailure | null
  selectConversation: (conversationId: string) => void
  createContact: (sex: ContactSex) => Promise<Conversation | null>
  sendTurn: (text: string) => Promise<boolean>
}

export function useChat(routeConversationId?: string): ChatState {
  const turnInFlight = useRef(false)
  const [config, setConfig] = useState<PublicConfig | null>(null)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(
    routeConversationId ?? null,
  )
  const [turns, setTurns] = useState<Turn[]>([])
  const [loadingConversations, setLoadingConversations] = useState(true)
  const [loadingTurns, setLoadingTurns] = useState(false)
  const [sending, setSending] = useState(false)
  const [creatingContact, setCreatingContact] = useState(false)
  const [error, setError] = useState<ChatFailure | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void Promise.all([getPublicConfig(controller.signal), getConversations(controller.signal)])
      .then(([receivedConfig, { conversations: received }]) => {
        setConfig(receivedConfig)
        setConversations(received)
        setSelectedConversationId((current) => current ?? received[0]?.id ?? null)
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
    if (routeConversationId !== undefined) setSelectedConversationId(routeConversationId)
  }, [routeConversationId])

  useEffect(() => {
    setTurns([])
    if (selectedConversationId === null) {
      setLoadingTurns(false)
      return
    }
    const controller = new AbortController()
    setLoadingTurns(true)
    setError(null)
    void getConversationTurns(selectedConversationId, controller.signal)
      .then(({ turns: received }) => setTurns(received))
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(failureFrom(reason))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingTurns(false)
      })
    return () => controller.abort()
  }, [selectedConversationId])

  const selectConversation = useCallback((conversationId: string) => {
    if (!turnInFlight.current) setSelectedConversationId(conversationId)
  }, [])

  const createContact = useCallback(async (sex: ContactSex): Promise<Conversation | null> => {
    if (creatingContact) return null
    setCreatingContact(true)
    setError(null)
    try {
      const { conversation } = await createContactRequest({ sex })
      setConversations((current) => [conversation, ...current])
      setSelectedConversationId(conversation.id)
      return conversation
    } catch (reason: unknown) {
      setError(failureFrom(reason))
      return null
    } finally {
      setCreatingContact(false)
    }
  }, [creatingContact])

  const sendTurn = useCallback(async (text: string): Promise<boolean> => {
    if (selectedConversationId === null || turnInFlight.current) return false
    const normalized = text.trim()
    if (!normalized) return false
    turnInFlight.current = true
    setSending(true)
    setError(null)
    try {
      const admitted = await createTurn(selectedConversationId, { text: normalized })
      setTurns((current) => upsertTurn(current, admitted))
      const terminal = await waitForTerminalTurn(admitted)
      setTurns((current) => upsertTurn(current, terminal))
      setConversations((current) => current.map((conversation) =>
        conversation.id === selectedConversationId
          ? { ...conversation, last_message_at: terminal.updated_at }
          : conversation,
      ))
      if (terminal.status !== 'completed') {
        setError({
          message: terminal.failure?.detail ?? 'Turn execution failed.',
          workflowRunId: terminal.execution_references.workflow_run_id,
          agentRunId: terminal.execution_references.agent_run_id,
          terminationReason: terminal.failure?.termination_reason ?? null,
        })
        return false
      }
      return true
    } catch (reason: unknown) {
      const failedTurn = reason instanceof ApiError ? reason.turn : null
      if (failedTurn !== null) setTurns((current) => upsertTurn(current, failedTurn))
      setError(failureFrom(reason))
      return false
    } finally {
      turnInFlight.current = false
      setSending(false)
    }
  }, [selectedConversationId])

  return {
    config,
    conversations,
    selectedConversationId,
    turns,
    loadingConversations,
    loadingTurns,
    sending,
    creatingContact,
    error,
    selectConversation,
    createContact,
    sendTurn,
  }
}
