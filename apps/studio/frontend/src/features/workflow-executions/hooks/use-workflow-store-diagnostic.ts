import { useEffect, useState } from 'react'
import { getWorkflowStoreDiagnostic } from '../fetch/get-workflow-store-diagnostic'
import type { WorkflowStoreDiagnostic } from '../schemas/workflow-store-diagnostic'

export interface WorkflowStoreDiagnosticRequest {
  data: WorkflowStoreDiagnostic | null
  loading: boolean
  error: string | null
}

const EMPTY_REQUEST: WorkflowStoreDiagnosticRequest = {
  data: null,
  loading: false,
  error: null,
}

export function useWorkflowStoreDiagnostic(
  traceId: string | undefined,
  workflowSpanId: string | undefined,
): WorkflowStoreDiagnosticRequest {
  const [request, setRequest] = useState<WorkflowStoreDiagnosticRequest>(EMPTY_REQUEST)

  useEffect(() => {
    if (traceId === undefined || workflowSpanId === undefined) {
      setRequest(EMPTY_REQUEST)
      return
    }

    const controller = new AbortController()
    setRequest({ data: null, loading: true, error: null })

    void getWorkflowStoreDiagnostic(traceId, workflowSpanId, controller.signal)
      .then((data) => {
        setRequest({ data, loading: false, error: null })
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        const message = error instanceof Error
          ? error.message
          : 'Failed to fetch Workflow Store diagnostics'
        setRequest({ data: null, loading: false, error: message })
      })

    return () => controller.abort()
  }, [traceId, workflowSpanId])

  return request
}
