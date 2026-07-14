import { z } from 'zod'
import {
  EvidenceDiagnosticSchema,
  EvidenceIntegritySchema,
  StoreDetailSchema,
} from '../../store-diagnostics/schemas/store-diagnostics'
import { NonEmptyPortableStringSchema } from '../../telemetry-contract/schemas/scalars'

export const WorkflowStoreDiagnosticSchema = z
  .object({
    trace_id: z.string().regex(/^[0-9a-f]{32}$/),
    workflow_span_id: z.string().regex(/^[0-9a-f]{16}$/),
    executable_type: z.enum(['workflow', 'subflow']),
    name: NonEmptyPortableStringSchema,
    state: StoreDetailSchema,
    integrity: EvidenceIntegritySchema,
  })
  .strict()
export type WorkflowStoreDiagnostic = z.infer<typeof WorkflowStoreDiagnosticSchema>

export const WorkflowEvidenceErrorResponseSchema = z
  .object({
    code: z.enum(['unsupported_contract', 'unidentifiable_workflow']),
    message: NonEmptyPortableStringSchema,
    diagnostics: z.array(EvidenceDiagnosticSchema),
  })
  .strict()

export const BackendWorkflowStoreProjectionFixtureSchema = z
  .object({
    case_name: NonEmptyPortableStringSchema,
    detail: WorkflowStoreDiagnosticSchema,
  })
  .strict()

export const BackendWorkflowStoreProjectionFixtureListSchema = z.array(
  BackendWorkflowStoreProjectionFixtureSchema,
)
export type BackendWorkflowStoreProjectionFixture = z.infer<
  typeof BackendWorkflowStoreProjectionFixtureSchema
>
