import { useState } from 'react'
import { sendMessage, SendMessageRequest } from './fetch'
import { useMessagesStore } from './store'

interface UseSendMessageResult {
  isLoading: boolean
  error: string | null
  sendMessage: (props: SendMessageRequest) => Promise<void>
}

const useSendMessage = (): UseSendMessageResult => {
  const { upsertMessages } = useMessagesStore()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const sendAndStoreMessage = async (props: SendMessageRequest) => {
    setIsLoading(true)
    setError(null)
    try {
      const newMessage = await sendMessage(props)
      upsertMessages(props.chat_id, [newMessage])
    } catch (error: any) {
      setError(error.message)
    } finally {
      setIsLoading(false)
    }
  }

  return { isLoading, error, sendMessage: sendAndStoreMessage }
}

export default useSendMessage
