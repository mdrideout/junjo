import { useNavigate } from 'react-router'
import { useAppDispatch } from '../../../root-store/hooks'
import { workflowPath } from '../../../util/telemetry-paths'
import type { OtelSpan } from '../../traces/schemas/schemas'
import type { StateEventSelection } from './state-event-identity'
import { spanSelection, WorkflowDetailStateActions } from './store/slice'
import { useWorkflowDetailRoute } from './workflow-detail-route-context'

/** Keep the displayed execution interval when selecting one of its Store writers. */
export function useSelectStoreTransition(
  ownerSpanId: string | undefined,
  spansById: ReadonlyMap<string, OtelSpan>,
) {
  const dispatch = useAppDispatch()
  const navigate = useNavigate()
  const route = useWorkflowDetailRoute()

  return (selection: StateEventSelection) => {
    const span = spansById.get(selection.spanId)
    if (span === undefined) return

    let ancestor = span
    const visited = new Set<string>()
    while (ancestor.span_id !== route.workflowSpanId && ancestor.parent_span_id && !visited.has(ancestor.span_id)) {
      visited.add(ancestor.span_id)
      const parent = spansById.get(ancestor.parent_span_id)
      if (!parent) break
      ancestor = parent
    }
    const inWorkflow = ancestor.span_id === route.workflowSpanId
    if (inWorkflow) dispatch(WorkflowDetailStateActions.selectSpan(spanSelection(span)))
    dispatch(WorkflowDetailStateActions.setActiveStateEvent({
      ...selection,
      viewOwnerSpanId: ownerSpanId ?? route.workflowSpanId,
    }))
    const { storeId, spanId, eventId, sequence } = selection
    dispatch(WorkflowDetailStateActions.setStateEventScrollTarget({ storeId, spanId, eventId, sequence }))
    // Sibling writers remain accessible through the writer link, outside this Graph.
    if (inWorkflow) navigate(workflowPath(
      route.serviceName,
      route.traceId,
      route.workflowSpanId,
      span.span_id,
    ), { replace: true })
  }
}
