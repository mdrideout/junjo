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
  generationConfig: z
    .object({
      stopSequences: z.array(z.string()).optional(),
      responseMimeType: z.string().optional(),
      temperature: z.number().optional(),
      topP: z.number().optional(),
      topK: z.number().optional(),
    })
    .optional(),
})

export type GeminiTextRequest = z.infer<typeof GeminiTextRequestSchema>
