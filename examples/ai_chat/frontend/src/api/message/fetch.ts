import { MessageRead, MessageReadSchema } from './schemas'

export const sendMessage = async (message: string): Promise<MessageRead> => {
  const response = await fetch(`http://127.0.0.1:8000/workflows/contact`, {
    method: 'POST',
    body: JSON.stringify({ message: message }),
    mode: 'cors',
    headers: {
      'Content-Type': 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Failed to send message: ${response.statusText}`)
  }

  const data = await response.json()

  try {
    // Validate the response data against our schema
    return MessageReadSchema.parse(data)
  } catch (error) {
    console.error('Data validation error:', error)
    throw new Error('Invalid data received from server')
  }
}
