import { z } from 'zod'

/**
 * Unified LiteLLM schemas for the Python backend.
 *
 * These match the backend Pydantic schemas in:
 * backend_python/app/features/llm_playground/schemas.py
 */

// LiteLLM Message Schema
export const LiteLLMMessageSchema = z.object({
  role: z.enum(['system', 'user', 'assistant']),
  content: z.string(),
})

export type LiteLLMMessage = z.infer<typeof LiteLLMMessageSchema>

// LiteLLM Reasoning Effort Schema
export const LiteLLMReasoningEffortSchema = z.enum(['minimal', 'low', 'medium', 'high'])

export type LiteLLMReasoningEffort = z.infer<typeof LiteLLMReasoningEffortSchema>

// LiteLLM JSON Schema Schema
export const LiteLLMJsonSchemaSchema = z.object({
  name: z.string(),
  strict: z.boolean().optional(),
  schema: z.record(z.any()),
})

export type LiteLLMJsonSchema = z.infer<typeof LiteLLMJsonSchemaSchema>

// LiteLLM Response Format Schema
export const LiteLLMResponseFormatSchema = z.union([
  z.object({ type: z.literal('json_object') }),
  z.object({ type: z.literal('text') }),
  z.object({
    type: z.literal('json_schema'),
    json_schema: LiteLLMJsonSchemaSchema,
  }),
])

export type LiteLLMResponseFormat = z.infer<typeof LiteLLMResponseFormatSchema>

// LiteLLM Request Schema
export const LiteLLMRequestSchema = z.object({
  // Required fields
  model: z.string(), // Provider prefix format: openai/gpt-4o, anthropic/claude-3-5-sonnet, gemini/gemini-2.5-pro
  messages: z.array(LiteLLMMessageSchema),

  // Common generation parameters
  temperature: z.number().min(0.0).max(2.0).optional(),
  max_tokens: z.number().positive().optional(),
  top_p: z.number().min(0.0).max(1.0).optional(),
  stop: z.array(z.string()).max(4).optional(),

  // Reasoning/thinking (unified - LiteLLM translates to provider-specific)
  reasoning_effort: LiteLLMReasoningEffortSchema.optional(),

  // OpenAI-specific (for reasoning models like o1)
  max_completion_tokens: z.number().positive().optional(),

  // JSON mode / Structured outputs
  json_mode: z.boolean().optional(),
  json_schema: z.record(z.any()).optional(),

  // Streaming (not implemented yet, but schema ready)
  stream: z.boolean().optional(),
})

export type LiteLLMRequest = z.infer<typeof LiteLLMRequestSchema>

// LiteLLM Usage Schema
export const LiteLLMUsageSchema = z.object({
  prompt_tokens: z.number(),
  completion_tokens: z.number(),
  total_tokens: z.number(),
})

export type LiteLLMUsage = z.infer<typeof LiteLLMUsageSchema>

// LiteLLM Choice Schema
export const LiteLLMChoiceSchema = z.object({
  index: z.number(),
  message: LiteLLMMessageSchema,
  finish_reason: z.string().nullable(),
})

export type LiteLLMChoice = z.infer<typeof LiteLLMChoiceSchema>

// LiteLLM Response Schema
export const LiteLLMResponseSchema = z.object({
  id: z.string(),
  object: z.string(),
  created: z.number(),
  model: z.string(),
  choices: z.array(LiteLLMChoiceSchema),
  usage: LiteLLMUsageSchema.optional(),
  reasoning_content: z.string().nullish(), // For OpenAI o1/Anthropic extended thinking (allows null or undefined)
})

export type LiteLLMResponse = z.infer<typeof LiteLLMResponseSchema>
