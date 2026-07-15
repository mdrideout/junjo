import { useMemo } from 'react'
import { useAppSelector } from '../../../root-store/hooks'
import type { WorkflowStoreDiagnostic } from '../schemas/workflow-store-diagnostic'

export interface WorkflowStoreDiagnosticRequest {
  data: WorkflowStoreDiagnostic | null
  loading: boolean
  error: string | null
}

export function useWorkflowStoreDiagnostic(
  traceId: string | undefined,
  workflowSpanId: string | undefined,
): WorkflowStoreDiagnosticRequest {
  const evidence = useAppSelector((state) =>
    traceId === undefined ? undefined : state.tracesState.traceEvidence[traceId],
  )
  const loading = useAppSelector((state) => state.tracesState.loading)
  const hasError = useAppSelector((state) => state.tracesState.error)

  return useMemo(() => {
    if (traceId === undefined || workflowSpanId === undefined) {
      return { data: null, loading: false, error: null }
    }
    const executable = evidence?.executables_by_span_id[workflowSpanId]
    if (executable?.executable_type !== 'workflow' && executable?.executable_type !== 'subflow') {
      return {
        data: null,
        loading,
        error: hasError ? 'Failed to fetch Workflow Store diagnostics' : null,
      }
    }
    const state = executable.store_id === null
      ? executable.unavailable_store
      : evidence?.stores_by_id[executable.store_id]?.detail
    if (state === null || state === undefined) {
      return {
        data: null,
        loading: false,
        error: 'Workflow Store evidence is unavailable',
      }
    }

    return {
      data: {
        trace_id: traceId,
        workflow_span_id: workflowSpanId,
        executable_type: executable.executable_type,
        name: executable.name,
        state,
        integrity: executable.integrity,
      },
      loading: false,
      error: null,
    }
  }, [evidence, hasError, loading, traceId, workflowSpanId])
}
