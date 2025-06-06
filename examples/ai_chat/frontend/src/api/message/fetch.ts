import { MessageRead, MessageReadSchema } from './schemas'

export interface SendMessageRequest {
  chat_id: string
  message: string
}

export const sendMessage = async (props: SendMessageRequest): Promise<void> => {
  const { chat_id, message } = props
  const response = await fetch(`http://127.0.0.1:8000/workflows-junjo/handle-message/${chat_id}`, {
    method: 'POST',
    body: JSON.stringify({ contact_id: null, chat_id, message }),
    mode: 'cors',
    headers: {
      'Content-Type': 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Failed to send message: ${response.statusText}`)
  }
}

export const fetchChatMessages = async (chat_id: string): Promise<MessageRead[]> => {
  const response = await fetch(`http://127.0.0.1:8000/api/message/${chat_id}`, {
    method: 'GET',
    mode: 'cors',
    headers: {
      'Content-Type': 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch chat messages: ${response.statusText}`)
  }

  const data = await response.json()

  try {
    // Validate the response data against our schema
    return MessageReadSchema.array().parse(data)
  } catch (error) {
    console.error('Data validation error:', error)
    throw new Error('Invalid data received from server')
  }
}

export const fetchNewerChatMessages = async (chat_id: string, message_id: string): Promise<MessageRead[]> => {
  const response = await fetch(`http://127.0.0.1:8000/api/message/newer-than/${chat_id}/${message_id}`, {
    method: 'GET',
    mode: 'cors',
    headers: {
      'Content-Type': 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch newer chat messages: ${response.statusText}`)
  }

  const data = await response.json()

  try {
    // Validate the response data against our schema
    return MessageReadSchema.array().parse(data)
  } catch (error) {
    console.error('Data validation error:', error)
    throw new Error('Invalid data received from server')
  }
}
