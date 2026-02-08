import { z } from 'zod'

/**
 * Schema for WAL flush response.
 * Matches backend Pydantic model: app/features/admin/router.py:FlushWALResponse
 */
export const FlushWALResponseSchema = z.object({
  success: z.boolean(),
  message: z.string(),
})

export type FlushWALResponse = z.infer<typeof FlushWALResponseSchema>
