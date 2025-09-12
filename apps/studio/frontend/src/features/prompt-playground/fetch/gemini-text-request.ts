import { API_HOST } from '../../../config'
import { GeminiTextRequest } from '../schemas/gemini-text-request'
import { GeminiTextResponseSchema } from '../schemas/gemini-text-response'

export const geminiTextRequest = async (payload: GeminiTextRequest) => {
  const response = await fetch(`${API_HOST}/llm/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error('Failed to generate content')
  }

  const data = await response.json()
  return GeminiTextResponseSchema.parse(data)
}
