import { z } from 'zod'
import { utcDatetimeSchema } from '../../util/datetime-utils'

// Python backend uses snake_case
export const ApiKeySchema = z.object({
  id: z.string(),
  key: z.string(),
  name: z.string(),
  created_at: utcDatetimeSchema, // Always UTC with 'Z' suffix from backend
})

export const ListApiKeysResponseSchema = z.array(ApiKeySchema)

export type ApiKey = z.infer<typeof ApiKeySchema>
export type ListApiKeysResponse = z.infer<typeof ListApiKeysResponseSchema>
