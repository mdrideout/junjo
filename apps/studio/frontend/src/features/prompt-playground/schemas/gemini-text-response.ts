import { z } from 'zod'

export const GeminiTextResponseSchema = z.object({
  candidates: z.array(
    z.object({
      content: z.object({
        parts: z.array(
          z.object({
            text: z.string(),
          }),
        ),
      }),
    }),
  ),
})

export type GeminiTextResponse = z.infer<typeof GeminiTextResponseSchema>
