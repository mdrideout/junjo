import { z } from 'zod'

export const GeminiTextRequestSchema = z.object({
  model: z.string().optional(),
  contents: z.array(
    z.object({
      parts: z.array(
        z.object({
          text: z.string(),
        }),
      ),
    }),
  ),
})

export type GeminiTextRequest = z.infer<typeof GeminiTextRequestSchema>
