import { z } from 'zod'

export const ApiKeySchema = z.object({
  Key: z.string(),
  Name: z.string(),
  CreatedAt: z.string(),
})

export const ListApiKeysResponseSchema = z.array(ApiKeySchema)

export type ApiKey = z.infer<typeof ApiKeySchema>
export type ListApiKeysResponse = z.infer<typeof ListApiKeysResponseSchema>
