import { z } from 'zod'
import { utcDatetimeSchema } from '../../util/datetime-utils'

export const EvaluationTokenScopeSchema = z.enum([
  'evaluation:read',
  'evaluation:write',
  'evidence:read',
])
export type EvaluationTokenScope = z.infer<typeof EvaluationTokenScopeSchema>

export const EvaluationTokenReadSchema = z
  .object({
    id: z.string().min(1),
    name: z.string().min(1),
    token: z.string(),
    scopes: z.array(EvaluationTokenScopeSchema).min(1),
    expires_at: utcDatetimeSchema.nullable(),
    created_by_user_id: z.string().min(1).nullable(),
    created_at: utcDatetimeSchema,
  })
  .strict()
export type EvaluationTokenRead = z.infer<typeof EvaluationTokenReadSchema>

export const EvaluationTokenListSchema = z
  .object({
    items: z.array(EvaluationTokenReadSchema),
    next_cursor: z.string().min(1).nullable(),
  })
  .strict()
export type EvaluationTokenList = z.infer<typeof EvaluationTokenListSchema>

export const EvaluationTokenCreateSchema = z
  .object({
    name: z.string().trim().min(1).max(128),
    scopes: z.array(EvaluationTokenScopeSchema).min(1),
    expires_at: utcDatetimeSchema.nullable(),
  })
  .strict()
export type EvaluationTokenCreate = z.infer<typeof EvaluationTokenCreateSchema>
