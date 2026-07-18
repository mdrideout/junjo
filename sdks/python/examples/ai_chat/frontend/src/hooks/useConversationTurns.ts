import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, createTurn, getConversationTurns, getTurn } from '../api/client'
import type { Turn } from '../api/schemas'
import { failureFrom, failureFromTurn, type ChatFailure } from './chatFailure'

const TERMINAL_STATUSES = new Set<Turn['status']>(['completed', 'failed', 'cancelled'])
const ACTIVE_TURN_POLL_INTERVAL_MS = 2000
const PASSIVE_REFRESH_INTERVAL_MS = 10000

function isActive(turn: Turn): boolean {
  return !TERMINAL_STATUSES.has(turn.status)
}

function upsertTurn(current: Turn[], received: Turn): Turn[] {
  return [...current.filter((turn) => turn.id !== received.id), received]
    .sort((left, right) => left.sequence - right.sequence)
}

export interface ConversationTurnsState {
  turns: Turn[]
  loading: boolean
  sending: boolean
  error: ChatFailure | null
  sendTurn: (text: string) => Promise<boolean>
}

export function useConversationTurns(conversationId: string): ConversationTurnsState {
  const [turns, setTurns] = useState<Turn[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [requestError, setRequestError] = useState<ChatFailure | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    let ignore = false

    const loadTurns = async (showLoading: boolean) => {
      if (showLoading) setLoading(true)
      try {
        const received = await getConversationTurns(conversationId, controller.signal)
        if (ignore) return
        setTurns(received.turns)
        setRequestError(null)
      } catch (reason: unknown) {
        if (!ignore && !controller.signal.aborted) setRequestError(failureFrom(reason))
      } finally {
        if (showLoading && !ignore) setLoading(false)
      }
    }

    void loadTurns(true)
    const interval = window.setInterval(() => void loadTurns(false), PASSIVE_REFRESH_INTERVAL_MS)

    return () => {
      ignore = true
      window.clearInterval(interval)
      controller.abort()
    }
  }, [conversationId])

  const activeTurn = useMemo(
    () => turns.find(isActive) ?? null,
    [turns],
  )
  const activeTurnId = activeTurn?.id ?? null

  useEffect(() => {
    if (activeTurnId === null) return

    const controller = new AbortController()
    let ignore = false
    let timeout: number | null = null

    const schedulePoll = () => {
      timeout = window.setTimeout(() => {
        void getTurn(activeTurnId, controller.signal)
          .then((received) => {
            if (ignore) return
            setTurns((current) => upsertTurn(current, received))
            setRequestError(null)
            if (isActive(received)) schedulePoll()
          })
          .catch((reason: unknown) => {
            if (ignore || controller.signal.aborted) return
            setRequestError(failureFrom(reason))
            schedulePoll()
          })
      }, ACTIVE_TURN_POLL_INTERVAL_MS)
    }

    schedulePoll()
    return () => {
      ignore = true
      if (timeout !== null) window.clearTimeout(timeout)
      controller.abort()
    }
  }, [activeTurnId])

  const sendTurn = useCallback(async (text: string): Promise<boolean> => {
    const normalized = text.trim()
    if (!normalized || submitting || activeTurnId !== null) return false
    setSubmitting(true)
    setRequestError(null)
    try {
      const admitted = await createTurn(conversationId, { text: normalized })
      setTurns((current) => upsertTurn(current, admitted))
      return true
    } catch (reason: unknown) {
      const failedTurn = reason instanceof ApiError ? reason.turn : null
      if (failedTurn !== null && failedTurn.conversation_id === conversationId) {
        setTurns((current) => upsertTurn(current, failedTurn))
      }
      setRequestError(failureFrom(reason))
      return false
    } finally {
      setSubmitting(false)
    }
  }, [activeTurnId, conversationId, submitting])

  const latestTurn = turns[turns.length - 1]
  const durableFailure = latestTurn === undefined ? null : failureFromTurn(latestTurn)

  return {
    turns,
    loading,
    sending: submitting || activeTurnId !== null,
    error: requestError ?? durableFailure,
    sendTurn,
  }
}
