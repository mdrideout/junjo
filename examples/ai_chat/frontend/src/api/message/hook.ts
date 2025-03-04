import { useState } from 'react'
import { sendMessage } from './fetch'
import { useChatsWithMembersStore } from './store'

interface UseSendMessageResult {
  isLoading: boolean
  error: string | null
  sendMessage: (message: string) => Promise<void>
}

const useSendMessage = (): UseSendMessageResult => {
  const { upsertMessages } = useChatsWithMembersStore()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const sendAndStoreMessage = async (message: string) => {
    setIsLoading(true)
    setError(null)
    try {
      const newMessage = await sendMessage(message)
      upsertMessages([newMessage])
    } catch (error: any) {
      setError(error.message)
    } finally {
      setIsLoading(false)
    }
  }

  return { isLoading, error, sendMessage: sendAndStoreMessage }
}

export default useSendMessage
