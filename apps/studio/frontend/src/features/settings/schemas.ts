import { z } from 'zod'

/**
 * Schema for WAL flush response.
 * Matches the backend response type: backend/server/src/features/admin.rs (FlushWALResponse)
 */
export const FlushWALResponseSchema = z.object({
  success: z.boolean(),
  message: z.string(),
})

export type FlushWALResponse = z.infer<typeof FlushWALResponseSchema>
