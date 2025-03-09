import { useRef, useState } from 'react'
import { useMessagesStore } from '../store'
import { fetchChatMessages, fetchNewerChatMessages } from '../fetch'

interface UseGetMessagesResult {
  isLoading: boolean
  error: string | null
  getChatMessages: (chat_id: string) => Promise<void>
  getNewerMessages: (chat_id: string, message_id: string) => Promise<void>
  pollForNewerMessages: (chat_id: string, message_id: string) => Promise<void>
}

const useGetMessages = (): UseGetMessagesResult => {
  const { upsertMessages } = useMessagesStore()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pollingActive = useRef(false)
  const pollingChatId = useRef<string | null>(null)
  const pollingMessageId = useRef<string | null>(null)

  const getChatMessages = async (chat_id: string) => {
    setIsLoading(true)
    setError(null)
    try {
      const newMessages = await fetchChatMessages(chat_id)
      upsertMessages(chat_id, newMessages)
    } catch (error: any) {
      setError(error.message)
    } finally {
      setIsLoading(false)
    }
  }

  const getNewerMessages = async (chat_id: string, message_id: string) => {
    setIsLoading(true)
    setError(null)
    try {
      const newMessages = await fetchNewerChatMessages(chat_id, message_id)
      upsertMessages(chat_id, newMessages)
    } catch (error: any) {
      setError(error.message)
    } finally {
      setIsLoading(false)
    }
  }

  const pollForNewerMessages = async (chat_id: string, message_id: string) => {
    // Update the polling to use new chat and message values
    pollingChatId.current = chat_id
    pollingMessageId.current = message_id

    // The recursive function
    async function recursiveFetch() {
      if (!pollingChatId.current || !pollingMessageId.current) {
        pollingActive.current = false
        return
      }

      await getNewerMessages(pollingChatId.current, pollingMessageId.current)
      await new Promise((resolve) => setTimeout(resolve, 3000))
      recursiveFetch()
    }

    // Start the polling and prevent concurrent polls
    if (pollingActive.current == false) {
      pollingActive.current = true
      recursiveFetch()
    }
  }

  return { isLoading, error, getChatMessages, getNewerMessages, pollForNewerMessages }
}

export default useGetMessages
