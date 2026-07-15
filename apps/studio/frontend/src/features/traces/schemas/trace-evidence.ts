import { z } from 'zod'
import {
  AgentExecutionSummarySchema,
  AgentOperationSchema,
  CancellationEvidenceSchema,
  CandidateEvidenceSchema,
  ExecutionErrorSchema,
  NestedExecutableReferenceSchema,
  ParentExecutableReferenceSchema,
} from '../../agent-executions/schemas/agent-execution'
import {
  EvidenceDiagnosticSchema,
  EvidenceIntegritySchema,
  PayloadEvidenceSchema,
  StoreDetailSchema,
} from '../../store-diagnostics/schemas/store-diagnostics'
import { OtelSpanSchema } from './schemas'

export const AgentExecutableAnnotationSchema = z
  .object({
    executable_type: z.literal('agent'),
    owner_span_id: z.string(),
    runtime_id: z.string(),
    store_id: z.string().nullable(),
    unavailable_store: StoreDetailSchema.nullable(),
    summary: AgentExecutionSummarySchema,
    definition: PayloadEvidenceSchema,
    input: PayloadEvidenceSchema.nullable(),
    output: PayloadEvidenceSchema.nullable(),
    input_candidate: CandidateEvidenceSchema.nullable(),
    history_candidate: CandidateEvidenceSchema.nullable(),
    error: ExecutionErrorSchema.nullable(),
    cancellation: CancellationEvidenceSchema.nullable(),
    integrity: EvidenceIntegritySchema,
  })
  .strict()
export type AgentExecutableAnnotation = z.infer<typeof AgentExecutableAnnotationSchema>

export const WorkflowExecutableAnnotationSchema = z
  .object({
    executable_type: z.enum(['workflow', 'subflow']),
    owner_span_id: z.string(),
    name: z.string(),
    definition_id: z.string().nullable(),
    runtime_id: z.string().nullable(),
    structural_id: z.string().nullable(),
    store_id: z.string().nullable(),
    unavailable_store: StoreDetailSchema.nullable(),
    integrity: EvidenceIntegritySchema,
  })
  .strict()

export const ExecutableAnnotationSchema = z.discriminatedUnion('executable_type', [
  AgentExecutableAnnotationSchema,
  WorkflowExecutableAnnotationSchema,
])
export type ExecutableAnnotation = z.infer<typeof ExecutableAnnotationSchema>

export const StoreAnnotationSchema = z
  .object({
    store_id: z.string(),
    owner_span_id: z.string(),
    owner_runtime_id: z.string().nullable(),
    owner_executable_type: z.enum(['workflow', 'subflow', 'agent']),
    detail: StoreDetailSchema,
    integrity: EvidenceIntegritySchema,
  })
  .strict()
export type StoreAnnotation = z.infer<typeof StoreAnnotationSchema>

export const ExecutableRelationshipsSchema = z
  .object({
    parent: ParentExecutableReferenceSchema.nullable(),
    nested: z.array(NestedExecutableReferenceSchema),
  })
  .strict()

export const TraceEvidenceDiagnosticSchema = z
  .object({
    scope: z.enum(['trace', 'executable']),
    owner_span_id: z.string().nullable(),
    issue: EvidenceDiagnosticSchema,
  })
  .strict()

export const TraceEvidenceSchema = z
  .object({
    trace_id: z.string(),
    spans: z.array(OtelSpanSchema),
    executables_by_span_id: z.record(ExecutableAnnotationSchema),
    operations_by_owner_runtime_id: z.record(z.record(AgentOperationSchema)),
    stores_by_id: z.record(StoreAnnotationSchema),
    relationships_by_owner_span_id: z.record(ExecutableRelationshipsSchema),
    diagnostics: z.array(TraceEvidenceDiagnosticSchema),
  })
  .strict()
export type TraceEvidence = z.infer<typeof TraceEvidenceSchema>
