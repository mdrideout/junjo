import { useState } from 'react'
import { useMessagesStore } from '../store'
import { fetchChatMessages, fetchNewerChatMessages } from '../fetch'

interface UseGetMessagesResult {
  isLoading: boolean
  error: string | null
  getChatMessages: (chat_id: string) => Promise<void>
  getNewerMessages: (chat_id: string, message_id: string) => Promise<void>
}

const useGetMessages = (): UseGetMessagesResult => {
  const { upsertMessages } = useMessagesStore()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

  return { isLoading, error, getChatMessages, getNewerMessages }
}

export default useGetMessages
