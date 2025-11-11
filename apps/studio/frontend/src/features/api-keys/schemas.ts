import { z } from 'zod'

// Python backend uses snake_case
export const ApiKeySchema = z.object({
  id: z.string(),
  key: z.string(),
  name: z.string(),
  created_at: z.string(),
})

export const ListApiKeysResponseSchema = z.array(ApiKeySchema)

export type ApiKey = z.infer<typeof ApiKeySchema>
export type ListApiKeysResponse = z.infer<typeof ListApiKeysResponseSchema>
