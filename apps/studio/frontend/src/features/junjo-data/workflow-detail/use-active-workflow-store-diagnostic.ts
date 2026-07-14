import { useAppSelector } from '../../../root-store/hooks'
import type { RootState } from '../../../root-store/store'
import type { OtelSpan } from '../../traces/schemas/schemas'
import {
  selectActiveStoreID,
  selectSpanById,
  selectWorkflowSpanByStoreId,
} from '../../traces/store/selectors'
import {
  useWorkflowStoreDiagnostic,
  type WorkflowStoreDiagnosticRequest,
} from '../../workflow-executions/hooks/use-workflow-store-diagnostic'

export interface ActiveWorkflowStoreDiagnostic {
  ownerSpan: OtelSpan | undefined
  request: WorkflowStoreDiagnosticRequest
}

/**
 * Resolve the Store owner selected by the Workflow detail UI and fetch its one
 * backend-authoritative diagnostic projection. The root Workflow is the
 * explicit fallback before the user selects a child span or transition.
 */
export function useActiveWorkflowStoreDiagnostic(
  traceId: string,
  defaultWorkflowSpanId: string,
): ActiveWorkflowStoreDiagnostic {
  const activeStoreId = useAppSelector((state: RootState) => selectActiveStoreID(state))
  const selectedOwner = useAppSelector((state: RootState) =>
    selectWorkflowSpanByStoreId(state, { traceId, storeId: activeStoreId }),
  )
  const defaultOwner = useAppSelector((state: RootState) =>
    selectSpanById(state, { traceId, spanId: defaultWorkflowSpanId }),
  )
  const ownerSpan = selectedOwner ?? defaultOwner
  const request = useWorkflowStoreDiagnostic(ownerSpan?.trace_id, ownerSpan?.span_id)

  return { ownerSpan, request }
}
