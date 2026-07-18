import { useCallback, useEffect, useState } from 'react'
import {
  createContact as createContactRequest,
  getConversations,
  getPublicConfig,
} from '../api/client'
import type { ContactSex, Conversation, PublicConfig } from '../api/schemas'
import { failureFrom, type ChatFailure } from './chatFailure'

const PASSIVE_REFRESH_INTERVAL_MS = 10000

export interface ChatShellState {
  config: PublicConfig | null
  conversations: Conversation[]
  loading: boolean
  creatingContact: boolean
  error: ChatFailure | null
  createContact: (sex: ContactSex) => Promise<Conversation | null>
}

export function useChatShell(): ChatShellState {
  const [config, setConfig] = useState<PublicConfig | null>(null)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const [creatingContact, setCreatingContact] = useState(false)
  const [error, setError] = useState<ChatFailure | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    let ignore = false

    const loadConversations = async () => {
      const received = await getConversations(controller.signal)
      if (!ignore) setConversations(received.conversations)
    }

    void Promise.all([getPublicConfig(controller.signal), loadConversations()])
      .then(([receivedConfig]) => {
        if (ignore) return
        setConfig(receivedConfig)
        setError(null)
      })
      .catch((reason: unknown) => {
        if (!ignore && !controller.signal.aborted) setError(failureFrom(reason))
      })
      .finally(() => {
        if (!ignore) setLoading(false)
      })

    const interval = window.setInterval(() => {
      void loadConversations().catch((reason: unknown) => {
        if (!ignore && !controller.signal.aborted) setError(failureFrom(reason))
      })
    }, PASSIVE_REFRESH_INTERVAL_MS)

    return () => {
      ignore = true
      window.clearInterval(interval)
      controller.abort()
    }
  }, [])

  const createContact = useCallback(async (sex: ContactSex): Promise<Conversation | null> => {
    if (creatingContact) return null
    setCreatingContact(true)
    setError(null)
    try {
      const { conversation } = await createContactRequest({ sex })
      setConversations((current) => [conversation, ...current])
      return conversation
    } catch (reason: unknown) {
      setError(failureFrom(reason))
      return null
    } finally {
      setCreatingContact(false)
    }
  }, [creatingContact])

  return {
    config,
    conversations,
    loading,
    creatingContact,
    error,
    createContact,
  }
}
