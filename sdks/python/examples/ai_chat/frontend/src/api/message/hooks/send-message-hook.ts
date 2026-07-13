import { useState } from 'react'
import { sendMessage, SendMessageRequest } from '../fetch'

interface UseSendMessageResult {
  isLoading: boolean
  error: string | null
  sendMessage: (props: SendMessageRequest) => Promise<void>
}

const useSendMessage = (): UseSendMessageResult => {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const sendAndStoreMessage = async (props: SendMessageRequest) => {
    setIsLoading(true)
    setError(null)
    try {
      await sendMessage(props)
    } catch (error: any) {
      setError(error.message)
    } finally {
      setIsLoading(false)
    }
  }

  return { isLoading, error, sendMessage: sendAndStoreMessage }
}

export default useSendMessage
