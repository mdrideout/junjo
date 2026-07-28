import { z } from 'zod'
import {
  JsonValueSchema,
  SafeNonNegativeIntegerSchema,
  SafePositiveIntegerSchema,
} from '../../telemetry-contract/schemas/scalars'
import { utcDatetimeSchema } from '../../../util/datetime-utils'

export const EvaluationIdSchema = z.string().min(1)

export const SemanticExecutionReferenceSchema = z
  .object({
    service_namespace: z.string(),
    service_name: z.string().min(1),
    executable_type: z.enum(['workflow', 'subflow', 'agent']),
    runtime_id: z.string().min(1),
  })
  .strict()
export type SemanticExecutionReference = z.infer<typeof SemanticExecutionReferenceSchema>

export const EvaluationDatasetStatusSchema = z.enum(['draft', 'locked'])
export type EvaluationDatasetStatus = z.infer<typeof EvaluationDatasetStatusSchema>

export const EvaluationDatasetSummarySchema = z
  .object({
    id: EvaluationIdSchema,
    application_key: z.string().min(1),
    key: z.string().min(1),
    name: z.string().min(1),
    status: EvaluationDatasetStatusSchema,
  })
  .strict()
export type EvaluationDatasetSummary = z.infer<typeof EvaluationDatasetSummarySchema>

export const EvaluationDatasetDetailSchema = EvaluationDatasetSummarySchema.extend({
  description: z.string().nullable(),
  created_by_user_id: EvaluationIdSchema.nullable(),
  created_at: utcDatetimeSchema,
  locked_at: utcDatetimeSchema.nullable(),
}).strict()
export type EvaluationDatasetDetail = z.infer<typeof EvaluationDatasetDetailSchema>

export const EvaluationRunStatusSchema = z.enum(['active', 'completed'])
export type EvaluationRunStatus = z.infer<typeof EvaluationRunStatusSchema>

export const EvaluationRunSchema = z
  .object({
    id: EvaluationIdSchema,
    dataset_id: EvaluationIdSchema,
    request_key: z.string().min(1),
    candidate_label: z.string().min(1),
    source_revision: z.string().min(1),
    status: EvaluationRunStatusSchema,
    created_by_user_id: EvaluationIdSchema.nullable(),
    created_at: utcDatetimeSchema,
    completed_at: utcDatetimeSchema.nullable(),
  })
  .strict()
export type EvaluationRun = z.infer<typeof EvaluationRunSchema>

export const EvaluationAttemptCountsSchema = z
  .object({
    total: SafeNonNegativeIntegerSchema,
    queued: SafeNonNegativeIntegerSchema,
    passed: SafeNonNegativeIntegerSchema,
    failed: SafeNonNegativeIntegerSchema,
    error: SafeNonNegativeIntegerSchema,
  })
  .strict()
export type EvaluationAttemptCounts = z.infer<typeof EvaluationAttemptCountsSchema>

export const EvaluationRunListItemSchema = z
  .object({
    run: EvaluationRunSchema,
    dataset: EvaluationDatasetSummarySchema,
    attempt_counts: EvaluationAttemptCountsSchema,
  })
  .strict()
export type EvaluationRunListItem = z.infer<typeof EvaluationRunListItemSchema>

export const EvaluationRunListPageSchema = z
  .object({
    items: z.array(EvaluationRunListItemSchema),
    next_cursor: z.string().min(1).nullable(),
  })
  .strict()
export type EvaluationRunListPage = z.infer<typeof EvaluationRunListPageSchema>

export const EvaluationCaseOriginSchema = z.enum(['authored', 'generated'])
export type EvaluationCaseOrigin = z.infer<typeof EvaluationCaseOriginSchema>

export const EvaluationTargetKindSchema = z.enum(['node', 'workflow', 'agent'])
export type EvaluationTargetKind = z.infer<typeof EvaluationTargetKindSchema>

export const EvaluationCaseSchema = z
  .object({
    id: EvaluationIdSchema,
    dataset_id: EvaluationIdSchema,
    case_key: z.string().min(1),
    ordinal: SafePositiveIntegerSchema,
    origin: EvaluationCaseOriginSchema,
    target_kind: EvaluationTargetKindSchema,
    target_key: z.string().min(1),
    input_version: SafePositiveIntegerSchema,
    input_json: JsonValueSchema,
    expectation_json: JsonValueSchema.nullable(),
    evaluator_key: z.string().min(1),
    evaluator_version: SafePositiveIntegerSchema,
    source_execution: SemanticExecutionReferenceSchema.nullable(),
    source_revision: z.string().min(1).nullable(),
    created_at: utcDatetimeSchema,
  })
  .strict()
export type EvaluationCase = z.infer<typeof EvaluationCaseSchema>

export const EvaluationAttemptStatusSchema = z.enum(['queued', 'passed', 'failed', 'error'])
export type EvaluationAttemptStatus = z.infer<typeof EvaluationAttemptStatusSchema>

export const EvaluationAttemptSchema = z
  .object({
    id: EvaluationIdSchema,
    run_id: EvaluationIdSchema,
    case_id: EvaluationIdSchema,
    status: EvaluationAttemptStatusSchema,
    score: z.number().finite().min(0).max(1).nullable(),
    reason: z.string().nullable(),
    duration_ms: SafeNonNegativeIntegerSchema.nullable(),
    subject_execution: SemanticExecutionReferenceSchema.nullable(),
    execution_bound_at: utcDatetimeSchema.nullable(),
    recorded_at: utcDatetimeSchema.nullable(),
  })
  .strict()
export type EvaluationAttempt = z.infer<typeof EvaluationAttemptSchema>

export const EvaluationRunCaseSchema = z
  .object({
    case: EvaluationCaseSchema,
    attempt: EvaluationAttemptSchema,
  })
  .strict()
export type EvaluationRunCase = z.infer<typeof EvaluationRunCaseSchema>

export const EvaluationRunDetailSchema = z
  .object({
    run: EvaluationRunSchema,
    dataset: EvaluationDatasetDetailSchema,
    cases: z.array(EvaluationRunCaseSchema),
  })
  .strict()
export type EvaluationRunDetail = z.infer<typeof EvaluationRunDetailSchema>
