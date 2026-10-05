import { z } from 'zod'
import { utcDatetimeSchema } from '../../util/datetime-utils'

/**
 * Response schema for API key creation.
 *
 * Used by:
 * - POST /api/v1/api-keys
 *
 * API keys remain available through the authenticated management list.
 *
 * Matches the backend response type:
 * backend/server/src/features/api_keys/repo.rs (ApiKey, serialized as APIKeyRead)
 */
export const ApiKeyCreateResponseSchema = z.object({
  id: z.string(),
  key: z.string(),
  name: z.string(),
  created_at: utcDatetimeSchema, // Always UTC with 'Z' suffix from backend
})

export type ApiKeyCreateResponse = z.infer<typeof ApiKeyCreateResponseSchema>

// Note: DELETE /api/v1/api-keys/{id} returns 204 No Content, no response schema needed
