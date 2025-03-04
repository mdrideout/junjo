import { useState } from 'react'
import { useMessagesStore } from '../store'
import { fetchChatMessages } from '../fetch'

interface UseGetMessagesResult {
  isLoading: boolean
  error: string | null
  getChatMessages: (chat_id: string) => Promise<void>
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

  return { isLoading, error, getChatMessages }
}

export default useGetMessages
