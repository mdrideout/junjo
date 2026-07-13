import { z } from 'zod'
import { ChatWithMembersRead, ChatWithMembersReadSchema } from './schemas'

export const fetchChatsWithMembers = async (): Promise<ChatWithMembersRead[]> => {
  const response = await fetch('http://127.0.0.1:8000/api/chat/with-members', {
    method: 'GET',
    mode: 'cors',
    headers: {
      'Content-Type': 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch contacts: ${response.statusText}`)
  }

  const data = await response.json()

  try {
    // Validate the response data as an array of ContactRead
    return z.array(ChatWithMembersReadSchema).parse(data)
  } catch (error) {
    console.error('Data validation error:', error)
    throw new Error('Invalid data received from server')
  }
}
