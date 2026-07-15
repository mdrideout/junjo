import { z } from 'zod'
import {
  JsonValueSchema,
  NonEmptyPortableStringSchema,
  PortableStringSchema,
  SafeNonNegativeIntegerSchema,
  SafePositiveIntegerSchema,
} from '../../telemetry-contract/schemas/scalars'
import {
  EvidenceDiagnosticSchema,
  EvidenceIntegritySchema,
  PayloadEvidenceSchema,
  StoreDetailSchema,
  type EvidenceDiagnostic,
  type EvidenceIntegrity,
  type PayloadEvidence,
  type StoreDetail,
} from '../../store-diagnostics/schemas/store-diagnostics'

export {
  JsonValueSchema,
  EvidenceDiagnosticSchema,
  EvidenceIntegritySchema,
  PayloadEvidenceSchema,
  StoreDetailSchema,
}
export type { EvidenceDiagnostic, EvidenceIntegrity, PayloadEvidence, StoreDetail }

export const ServiceIdentitySchema = z
  .object({
    namespace: PortableStringSchema,
    name: NonEmptyPortableStringSchema,
    version: NonEmptyPortableStringSchema.nullable(),
  })
  .strict()
export type ServiceIdentity = z.infer<typeof ServiceIdentitySchema>

export const TraceIdSchema = z.string().regex(/^[0-9a-f]{32}$/, 'Trace ID must be 32 lowercase hexadecimal characters')
export const SpanIdSchema = z.string().regex(/^[0-9a-f]{16}$/, 'Span ID must be 16 lowercase hexadecimal characters')
export const AgentStructuralIdSchema = z
  .string()
  .regex(/^agent_sha256:[0-9a-f]{64}$/, 'Agent structural ID must contain a lowercase SHA-256 digest')
export const ToolStructuralIdSchema = z
  .string()
  .regex(/^tool_sha256:[0-9a-f]{64}$/, 'Tool structural ID must contain a lowercase SHA-256 digest')

export const CandidateEvidenceSchema = z
  .object({
    available: z.boolean(),
    payload: PayloadEvidenceSchema.nullable(),
    unavailable_reason: z.enum([
      'cancelled',
      'not_returned',
      'not_invoked',
      'service_failed',
      'not_json_serializable',
      'contract_evidence_missing',
    ]).nullable(),
  })
  .strict()
  .superRefine((candidate, context) => {
    if (candidate.available && candidate.payload === null) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Available candidate evidence requires a payload',
        path: ['payload'],
      })
    }

    if (candidate.available && candidate.unavailable_reason !== null) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Available candidate evidence cannot have an unavailable reason',
        path: ['unavailable_reason'],
      })
    }

    if (!candidate.available && candidate.payload !== null) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Unavailable candidate evidence cannot have a payload',
        path: ['payload'],
      })
    }

    if (!candidate.available && candidate.unavailable_reason === null) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Unavailable candidate evidence requires a reason',
        path: ['unavailable_reason'],
      })
    }
  })
export type CandidateEvidence = z.infer<typeof CandidateEvidenceSchema>

export const AgentOutcomeSchema = z.enum(['completed', 'failed', 'cancelled'])
export type AgentOutcome = z.infer<typeof AgentOutcomeSchema>

export const AgentTerminationReasonSchema = z.enum([
  'final_output',
  'input_validation_error',
  'history_validation_error',
  'limit_exceeded',
  'model_error',
  'model_response_error',
  'unknown_tool',
  'tool_input_validation_error',
  'tool_error',
  'tool_output_validation_error',
  'output_validation_error',
  'cancelled',
  'internal_error',
])
export type AgentTerminationReason = z.infer<typeof AgentTerminationReasonSchema>

const UsageObservationSchema = z
  .object({
    sum: SafeNonNegativeIntegerSchema,
    observations: SafePositiveIntegerSchema,
  })
  .strict()

const UsageFieldSchema = z.enum([
  'inputTokens',
  'outputTokens',
  'cachedInputTokens',
  'reasoningTokens',
  'totalTokens',
])

export const AgentUsageSchema = z
  .object({
    model_responses: SafeNonNegativeIntegerSchema,
    fields: z.record(UsageFieldSchema, UsageObservationSchema),
  })
  .strict()
export type AgentUsage = z.infer<typeof AgentUsageSchema>

export const ModelUsageSchema = z
  .object({
    input_tokens: SafeNonNegativeIntegerSchema.nullable(),
    output_tokens: SafeNonNegativeIntegerSchema.nullable(),
    cached_input_tokens: SafeNonNegativeIntegerSchema.nullable(),
    reasoning_tokens: SafeNonNegativeIntegerSchema.nullable(),
    total_tokens: SafeNonNegativeIntegerSchema.nullable(),
  })
  .strict()
export type ModelUsage = z.infer<typeof ModelUsageSchema>

export const RequestedToolCallSchema = z
  .object({
    call_id: NonEmptyPortableStringSchema,
    ordinal: SafePositiveIntegerSchema,
    tool_name: NonEmptyPortableStringSchema,
    observed_tool_operation: z.boolean(),
    admission: z.enum(['admitted', 'not_admitted', 'unknown']),
    reason: z.enum([
      'execution_interrupted',
      'store_evidence_unavailable',
      'tool_input_validation_error',
      'unknown_tool',
      'limit_exceeded',
      'batch_preflight_rejected',
    ]).nullable(),
  })
  .strict()
  .superRefine((toolCall, context) => {
    if (toolCall.admission === 'admitted') {
      const expectedReason = toolCall.observed_tool_operation ? null : 'execution_interrupted'
      if (toolCall.reason !== expectedReason) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Admitted Tool-call execution evidence is inconsistent',
        })
      }
    } else if (toolCall.admission === 'not_admitted') {
      if (![
        'tool_input_validation_error',
        'unknown_tool',
        'limit_exceeded',
        'batch_preflight_rejected',
      ].includes(toolCall.reason ?? '')) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Non-admitted Tool calls require a rejection reason',
          path: ['reason'],
        })
      }
    } else if (toolCall.reason !== 'store_evidence_unavailable') {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Unknown admission requires unavailable Store evidence',
        path: ['reason'],
      })
    }
  })
export type RequestedToolCall = z.infer<typeof RequestedToolCallSchema>

export const AgentExecutionCountsSchema = z
  .object({
    operations: SafeNonNegativeIntegerSchema,
    model_requests: SafeNonNegativeIntegerSchema,
    tool_calls: z
      .object({
        requested: SafeNonNegativeIntegerSchema,
        admitted: SafeNonNegativeIntegerSchema,
        started: SafeNonNegativeIntegerSchema,
        completed: SafeNonNegativeIntegerSchema,
      })
      .strict()
      .superRefine((counts, context) => {
        if (!(counts.completed <= counts.started && counts.started <= counts.admitted && counts.admitted <= counts.requested)) {
          context.addIssue({
            code: z.ZodIssueCode.custom,
            message: 'Tool counts must satisfy completed <= started <= admitted <= requested',
          })
        }
      }),
  })
  .strict()
export type AgentExecutionCounts = z.infer<typeof AgentExecutionCountsSchema>

export const AgentExecutionSummarySchema = z
  .object({
    trace_id: TraceIdSchema,
    agent_span_id: SpanIdSchema,
    service: ServiceIdentitySchema,
    agent_key: NonEmptyPortableStringSchema,
    agent_name: NonEmptyPortableStringSchema,
    structural_id: AgentStructuralIdSchema,
    definition_id: NonEmptyPortableStringSchema,
    runtime_id: NonEmptyPortableStringSchema,
    start_time: z.string().datetime({ offset: true }),
    end_time: z.string().datetime({ offset: true }),
    duration_ns: SafeNonNegativeIntegerSchema,
    outcome: AgentOutcomeSchema,
    termination_reason: AgentTerminationReasonSchema,
    limits: z
      .object({
        model_requests: SafePositiveIntegerSchema,
        tool_calls: SafePositiveIntegerSchema,
      })
      .strict(),
    counts: AgentExecutionCountsSchema,
    usage: AgentUsageSchema,
  })
  .strict()
  .superRefine((summary, context) => {
    const expectedOutcome = summary.termination_reason === 'final_output'
      ? 'completed'
      : summary.termination_reason === 'cancelled'
        ? 'cancelled'
        : 'failed'
    if (summary.outcome !== expectedOutcome) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Agent outcome does not match its termination reason',
        path: ['outcome'],
      })
    }
    if (summary.counts.operations < summary.counts.model_requests) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Operation count cannot be smaller than model request count',
        path: ['counts', 'operations'],
      })
    }
    if (summary.counts.model_requests > summary.limits.model_requests) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Model request count exceeds its limit',
        path: ['counts', 'model_requests'],
      })
    }
    if (summary.counts.tool_calls.admitted > summary.limits.tool_calls) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Admitted Tool count exceeds its limit',
        path: ['counts', 'tool_calls', 'admitted'],
      })
    }
    if (summary.usage.model_responses > summary.counts.model_requests) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Validated model responses cannot exceed model requests',
        path: ['usage', 'model_responses'],
      })
    }
  })
export type AgentExecutionSummary = z.infer<typeof AgentExecutionSummarySchema>

export const ExecutionErrorSchema = z
  .object({
    type: NonEmptyPortableStringSchema,
    message: PortableStringSchema.nullable(),
    stacktrace: PortableStringSchema.nullable(),
  })
  .strict()
export type ExecutionError = z.infer<typeof ExecutionErrorSchema>

export const CancellationEvidenceSchema = z
  .object({
    reason: NonEmptyPortableStringSchema,
  })
  .strict()
export type CancellationEvidence = z.infer<typeof CancellationEvidenceSchema>

const OperationBaseSchema = z.object({
  sequence: SafePositiveIntegerSchema,
  span_id: SpanIdSchema,
  start_time: z.string().datetime({ offset: true }),
  end_time: z.string().datetime({ offset: true }),
  duration_ns: SafeNonNegativeIntegerSchema,
  outcome: AgentOutcomeSchema,
  error: ExecutionErrorSchema.nullable(),
  cancellation: CancellationEvidenceSchema.nullable(),
})

export const ModelOperationSchema = OperationBaseSchema.extend({
  operation_type: z.literal('model_request'),
  ordinal: SafePositiveIntegerSchema,
  state_revision: SafeNonNegativeIntegerSchema,
  driver_key: NonEmptyPortableStringSchema,
  provider: NonEmptyPortableStringSchema,
  model_name: NonEmptyPortableStringSchema,
  request: PayloadEvidenceSchema,
  response_candidate: CandidateEvidenceSchema,
  response_type: z.enum(['final_output', 'tool_calls']).nullable(),
  response: PayloadEvidenceSchema.nullable(),
  usage: ModelUsageSchema.nullable(),
  requested_tool_calls: z.array(RequestedToolCallSchema),
}).strict()
export type ModelOperation = z.infer<typeof ModelOperationSchema>

export const ToolOperationSchema = OperationBaseSchema.extend({
  operation_type: z.literal('tool'),
  call_id: NonEmptyPortableStringSchema,
  ordinal: SafePositiveIntegerSchema,
  tool_name: NonEmptyPortableStringSchema,
  tool_structural_id: ToolStructuralIdSchema,
  state_revision_before: SafeNonNegativeIntegerSchema,
  state_revision_after: SafeNonNegativeIntegerSchema.nullable(),
  requested_arguments: PayloadEvidenceSchema,
  arguments: PayloadEvidenceSchema.nullable(),
  result_candidate: CandidateEvidenceSchema,
  result: PayloadEvidenceSchema.nullable(),
}).strict()
export type ToolOperation = z.infer<typeof ToolOperationSchema>

export const AgentOperationSchema = z.discriminatedUnion('operation_type', [
  ModelOperationSchema,
  ToolOperationSchema,
]).superRefine((operation, context) => {
  if (operation.outcome === 'completed' && (operation.error !== null || operation.cancellation !== null)) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Completed operation cannot contain error or cancellation evidence',
      path: ['outcome'],
    })
  }
  if (operation.outcome === 'failed' && operation.cancellation !== null) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Failed operation cannot contain cancellation evidence',
      path: ['outcome'],
    })
  }
  if (operation.outcome === 'cancelled' && (operation.error !== null || operation.cancellation === null)) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: 'Cancelled operation requires only cancellation evidence',
      path: ['outcome'],
    })
  }

  if (operation.operation_type === 'model_request') {
    if ((operation.response_type === null) !== (operation.response === null)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Validated model response type and payload must be present together',
        path: ['response'],
      })
    }
    if (operation.response_type !== 'tool_calls' && operation.requested_tool_calls.length > 0) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Requested Tool calls require a validated Tool-calls response',
        path: ['requested_tool_calls'],
      })
    }
    if (operation.outcome === 'completed' && operation.response === null) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Completed Model operation requires a validated response',
        path: ['response'],
      })
    }
    if (operation.outcome !== 'completed' && (operation.response !== null || operation.usage !== null)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Failed or cancelled Model operation cannot carry response evidence',
        path: ['response'],
      })
    }
    if (operation.response_type === null && operation.usage !== null) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Usage requires a validated model response',
        path: ['usage'],
      })
    }
  } else {
    if (operation.outcome === 'completed'
      && (operation.arguments === null || operation.result === null || operation.state_revision_after === null)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Completed Tool operation requires validated arguments, result, and committed revision',
      })
    }
    if (operation.outcome !== 'completed'
      && (operation.result !== null || operation.state_revision_after !== null)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Failed or cancelled Tool operation cannot carry committed result evidence',
        path: ['result'],
      })
    }
    if ((operation.result === null) !== (operation.state_revision_after === null)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Tool result and committed revision must be present together',
        path: ['result'],
      })
    }
  }
})
export type AgentOperation = z.infer<typeof AgentOperationSchema>

export const ExecutableTypeSchema = z.enum([
  'workflow',
  'subflow',
  'node',
  'run_concurrent',
  'agent',
])
export type ExecutableType = z.infer<typeof ExecutableTypeSchema>

export const ParentExecutableReferenceSchema = z
  .object({
    executable_type: ExecutableTypeSchema,
    trace_id: TraceIdSchema,
    physical_parent_span_id: SpanIdSchema,
    span_id: SpanIdSchema,
    service: ServiceIdentitySchema,
    definition_id: NonEmptyPortableStringSchema,
    runtime_id: NonEmptyPortableStringSchema,
    structural_id: NonEmptyPortableStringSchema,
    name: NonEmptyPortableStringSchema,
  })
  .strict()
export type ParentExecutableReference = z.infer<typeof ParentExecutableReferenceSchema>

const NestedExecutableReferenceBaseSchema = z.object({
    parent_operation_sequence: SafePositiveIntegerSchema,
    parent_operation_span_id: SpanIdSchema,
    trace_id: TraceIdSchema,
    span_id: SpanIdSchema,
    service: ServiceIdentitySchema,
    definition_id: NonEmptyPortableStringSchema,
    runtime_id: NonEmptyPortableStringSchema,
    name: NonEmptyPortableStringSchema,
})

export const NestedExecutableReferenceSchema = z.discriminatedUnion('executable_type', [
  NestedExecutableReferenceBaseSchema.extend({
    executable_type: z.literal('workflow'),
    structural_id: NonEmptyPortableStringSchema,
  }).strict(),
  NestedExecutableReferenceBaseSchema.extend({
    executable_type: z.literal('agent'),
    structural_id: AgentStructuralIdSchema,
  }).strict(),
])
export type NestedExecutableReference = z.infer<typeof NestedExecutableReferenceSchema>

export const AgentEvidenceErrorResponseSchema = z
  .object({
    code: z.enum(['unsupported_contract', 'unidentifiable_agent']),
    message: NonEmptyPortableStringSchema,
    diagnostics: z.array(EvidenceDiagnosticSchema),
  })
  .strict()
export type AgentEvidenceErrorResponse = z.infer<typeof AgentEvidenceErrorResponseSchema>

export const AgentExecutionDetailSchema = z
  .object({
    summary: AgentExecutionSummarySchema,
    definition: PayloadEvidenceSchema,
    input: PayloadEvidenceSchema.nullable(),
    output: PayloadEvidenceSchema.nullable(),
    input_candidate: CandidateEvidenceSchema.nullable(),
    history_candidate: CandidateEvidenceSchema.nullable(),
    operations: z.array(AgentOperationSchema),
    state: StoreDetailSchema,
    parent_executable: ParentExecutableReferenceSchema.nullable(),
    nested_executables: z.array(NestedExecutableReferenceSchema),
    error: ExecutionErrorSchema.nullable(),
    cancellation: CancellationEvidenceSchema.nullable(),
    integrity: EvidenceIntegritySchema,
  })
  .strict()
  .superRefine((detail, context) => {
    if (detail.summary.outcome === 'completed') {
      if (detail.error !== null || detail.cancellation !== null || detail.output === null) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Completed Agent execution requires output and cannot contain error or cancellation evidence',
        })
      }
    } else if (detail.summary.outcome === 'failed') {
      if (detail.cancellation !== null || detail.output !== null) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Failed Agent execution cannot contain cancellation or output evidence',
        })
      }
    } else if (detail.error !== null || detail.cancellation === null || detail.output !== null) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Cancelled Agent execution requires only cancellation evidence and no output',
      })
    }
  })
export type AgentExecutionDetail = z.infer<typeof AgentExecutionDetailSchema>

export const AgentExecutionSummaryListSchema = z.array(AgentExecutionSummarySchema)

export const BackendAgentProjectionFixtureSchema = z
  .object({
    case_name: NonEmptyPortableStringSchema,
    summary: AgentExecutionSummarySchema,
    detail: AgentExecutionDetailSchema,
  })
  .strict()

export const BackendAgentProjectionFixtureListSchema = z.array(BackendAgentProjectionFixtureSchema)
export type BackendAgentProjectionFixture = z.infer<typeof BackendAgentProjectionFixtureSchema>
