import { z } from 'zod'
import { utcDatetimeSchema } from '../../util/datetime-utils'

/**
 * Response schema for API key creation.
 *
 * Used by:
 * - POST /api_keys
 *
 * API keys remain available through the authenticated management list.
 *
 * Matches backend Pydantic schema:
 * backend/app/db_sqlite/api_keys/schemas.py (APIKeyRead with key field)
 */
export const ApiKeyCreateResponseSchema = z.object({
  id: z.string(),
  key: z.string(),
  name: z.string(),
  created_at: utcDatetimeSchema, // Always UTC with 'Z' suffix from backend
})

export type ApiKeyCreateResponse = z.infer<typeof ApiKeyCreateResponseSchema>

// Note: DELETE /api_keys/{id} returns 204 No Content, no response schema needed
