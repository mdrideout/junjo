import { z } from 'zod'
import { utcDatetimeSchema } from '../../lib/datetime-utils'

/**
 * Response schema for API key creation.
 *
 * Used by:
 * - POST /api_keys
 *
 * This is the ONLY time the full API key (with secret) is returned.
 * Subsequent GET requests only return APIKeyRead which excludes the secret key.
 *
 * Matches backend Pydantic schema:
 * backend/app/db_sqlite/api_keys/schemas.py (APIKeyRead with key field)
 */
export const ApiKeyCreateResponseSchema = z.object({
  id: z.string(),
  key: z.string(), // Secret API key (only shown once on creation)
  name: z.string(),
  created_at: utcDatetimeSchema, // Always UTC with 'Z' suffix from backend
})

export type ApiKeyCreateResponse = z.infer<typeof ApiKeyCreateResponseSchema>

// Note: DELETE /api_keys/{id} returns 204 No Content, no response schema needed
