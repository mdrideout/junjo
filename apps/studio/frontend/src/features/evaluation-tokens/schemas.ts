import { z } from 'zod'
import { utcDatetimeSchema } from '../../util/datetime-utils'

const EVALUATION_TOKEN_PREFIX = /^junjo_eval_[A-Za-z0-9_-]{12}$/
const EVALUATION_TOKEN = /^junjo_eval_[A-Za-z0-9_-]{12}\.[A-Za-z0-9_-]{43}$/

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
    prefix: z.string().regex(EVALUATION_TOKEN_PREFIX),
    scopes: z.array(EvaluationTokenScopeSchema).min(1),
    expires_at: utcDatetimeSchema.nullable(),
    revoked_at: utcDatetimeSchema.nullable(),
    created_by_user_id: z.string().min(1).nullable(),
    created_at: utcDatetimeSchema,
  })
  .strict()
export type EvaluationTokenRead = z.infer<typeof EvaluationTokenReadSchema>

export const EvaluationTokenCreatedSchema = EvaluationTokenReadSchema.extend({
  token: z.string().regex(EVALUATION_TOKEN),
}).strict()
export type EvaluationTokenCreated = z.infer<typeof EvaluationTokenCreatedSchema>

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
