import { getApiHost } from '../../../config'
import {
  WorkflowEvidenceErrorResponseSchema,
  WorkflowStoreDiagnosticSchema,
  type WorkflowStoreDiagnostic,
} from '../schemas/workflow-store-diagnostic'

const TraceIdSchema = WorkflowStoreDiagnosticSchema.shape.trace_id
const SpanIdSchema = WorkflowStoreDiagnosticSchema.shape.workflow_span_id

export async function getWorkflowStoreDiagnostic(
  traceId: string,
  workflowSpanId: string,
  signal?: AbortSignal,
): Promise<WorkflowStoreDiagnostic> {
  const trace = TraceIdSchema.parse(traceId)
  const span = SpanIdSchema.parse(workflowSpanId)
  const endpoint = `/api/v1/workflow-executions/${trace}/${span}/store`
  const response = await fetch(`${getApiHost()}${endpoint}`, {
    credentials: 'include',
    signal,
  })
  if (!response.ok) {
    const fallback = `Failed to fetch Workflow Store diagnostics (${response.status})`
    if (response.status !== 409) throw new Error(fallback)
    const body: unknown = await response.json().catch(() => null)
    const semantic = WorkflowEvidenceErrorResponseSchema.safeParse(body)
    if (!semantic.success) throw new Error(fallback)
    const diagnostics = semantic.data.diagnostics
      .map(diagnostic => `${diagnostic.code} at ${diagnostic.path}`)
      .join('; ')
    throw new Error(
      `${semantic.data.code}: ${semantic.data.message}${diagnostics ? ` — ${diagnostics}` : ''}`,
    )
  }
  return WorkflowStoreDiagnosticSchema.parse(await response.json())
}
