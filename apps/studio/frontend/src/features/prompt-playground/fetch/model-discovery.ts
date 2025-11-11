import { getApiHost } from '../../../config'

/**
 * Model information from the unified Python backend.
 *
 * Matches backend schema:
 * backend_python/app/features/llm_playground/schemas.py:ModelInfo
 */
export interface ModelInfo {
  id: string // Full model name with provider prefix (e.g., 'openai/gpt-4o')
  provider: string // Provider name: 'openai', 'anthropic', 'gemini'
  display_name: string // Human-readable model name
  supports_reasoning: boolean // Supports reasoning/thinking
  supports_vision: boolean // Supports vision/image inputs
  max_tokens: number | null // Maximum context tokens
}

interface ModelsResponse {
  models: ModelInfo[]
}

/**
 * Fetch all available models from all providers
 */
export const fetchAllModels = async (): Promise<ModelInfo[]> => {
  const endpoint = '/llm/models'
  const apiHost = getApiHost(endpoint)

  const response = await fetch(`${apiHost}${endpoint}`, {
    method: 'GET',
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch models: ${response.statusText}`)
  }

  const data: ModelsResponse = await response.json()
  return data.models
}

/**
 * Fetch models for a specific provider (openai, anthropic, gemini)
 */
export const fetchModelsByProvider = async (provider: string): Promise<ModelInfo[]> => {
  const endpoint = `/llm/providers/${provider}/models`
  const apiHost = getApiHost(endpoint)

  const response = await fetch(`${apiHost}${endpoint}`, {
    method: 'GET',
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch models for ${provider}: ${response.statusText}`)
  }

  const data: ModelsResponse = await response.json()
  return data.models
}

/**
 * Force refresh models from provider API (bypass cache)
 */
export const refreshModelsByProvider = async (provider: string): Promise<ModelInfo[]> => {
  const endpoint = `/llm/providers/${provider}/models/refresh`
  const apiHost = getApiHost(endpoint)

  const response = await fetch(`${apiHost}${endpoint}`, {
    method: 'POST',
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error(`Failed to refresh models for ${provider}: ${response.statusText}`)
  }

  // Backend returns the refreshed models directly
  const data: ModelsResponse = await response.json()
  return data.models
}
