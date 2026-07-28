import { z } from 'zod'
import { EvaluationIdSchema } from './evaluation-runs'

export const EvaluationRunListQuerySchema = z
  .object({
    dataset_id: EvaluationIdSchema.optional(),
    cursor: z.string().min(1).optional(),
    limit: z.number().int().positive().max(100).default(50),
  })
  .strict()
export type EvaluationRunListQuery = z.infer<typeof EvaluationRunListQuerySchema>

export const EvaluationRunComparisonQuerySchema = z
  .object({
    baseline_run_id: EvaluationIdSchema,
    candidate_run_id: EvaluationIdSchema,
  })
  .strict()
  .refine((query) => query.baseline_run_id !== query.candidate_run_id, {
    message: 'Baseline and candidate run IDs must differ',
    path: ['candidate_run_id'],
  })
export type EvaluationRunComparisonQuery = z.infer<typeof EvaluationRunComparisonQuerySchema>

export function evaluationRunListQueryFromSearchParams(
  parameters: URLSearchParams,
): EvaluationRunListQuery | null {
  const limitText = parameters.get('limit')
  const parsed = EvaluationRunListQuerySchema.safeParse({
    dataset_id: parameters.get('dataset_id') || undefined,
    cursor: parameters.get('cursor') || undefined,
    limit: limitText === null ? undefined : Number(limitText),
  })
  return parsed.success ? parsed.data : null
}

export function evaluationRunComparisonQueryFromSearchParams(
  parameters: URLSearchParams,
): EvaluationRunComparisonQuery | null {
  const parsed = EvaluationRunComparisonQuerySchema.safeParse({
    baseline_run_id: parameters.get('baseline_run_id'),
    candidate_run_id: parameters.get('candidate_run_id'),
  })
  return parsed.success ? parsed.data : null
}

export function getEvaluationRunListQueryKey(query: EvaluationRunListQuery): string {
  return JSON.stringify(EvaluationRunListQuerySchema.parse(query))
}
