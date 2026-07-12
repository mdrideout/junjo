import { z } from 'zod'

/**
 * Schema for individual model information.
 *
 * Represents a single model returned from the backend.
 *
 * Matches backend Pydantic schema:
 * backend/app/features/llm_playground/schemas.py (ModelInfo)
 */
export const ModelInfoSchema = z.object({
  id: z.string(),
  provider: z.string(),
  display_name: z.string(),
  supports_reasoning: z.boolean(),
  supports_vision: z.boolean(),
  max_tokens: z.number().nullable(),
})

/**
 * Response schema for model discovery/refresh operations.
 *
 * Used by:
 * - POST /llm/providers/{provider}/models/refresh
 *
 * Returns a list of available models for a given provider.
 */
export const ModelsResponseSchema = z.object({
  models: z.array(ModelInfoSchema),
})

export type ModelInfo = z.infer<typeof ModelInfoSchema>
export type ModelsResponse = z.infer<typeof ModelsResponseSchema>
