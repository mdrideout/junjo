import { getApiHost } from '../../../config'
import {
  LiteLLMRequest,
  LiteLLMResponseSchema,
  type LiteLLMResponse,
} from '../schemas/litellm-request'

/**
 * Send a request to the unified LiteLLM endpoint via Python backend.
 *
 * LiteLLM automatically routes to the correct provider based on model name:
 * - openai/gpt-4o → OpenAI
 * - anthropic/claude-3-5-sonnet → Anthropic
 * - gemini/gemini-2.5-pro → Gemini
 */
export const litellmRequest = async (payload: LiteLLMRequest): Promise<LiteLLMResponse> => {
  const endpoint = '/llm/generate'
  const apiHost = getApiHost(endpoint)

  const response = await fetch(`${apiHost}${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
    credentials: 'include', // Required for session-based authentication
  })

  if (!response.ok) {
    // Try to extract error message from response body
    let errorMessage = 'Failed to generate content'
    try {
      const errorData = await response.json()
      // Backend returns errors in 'detail' field (FastAPI standard)
      if (errorData.detail) {
        errorMessage = errorData.detail
      } else if (errorData.error) {
        errorMessage = errorData.error
      }
    } catch {
      // If parsing fails, use HTTP status text
      errorMessage = `Failed to generate content: ${response.status} ${response.statusText}`
    }
    throw new Error(errorMessage)
  }

  const data = await response.json()
  return LiteLLMResponseSchema.parse(data)
}
