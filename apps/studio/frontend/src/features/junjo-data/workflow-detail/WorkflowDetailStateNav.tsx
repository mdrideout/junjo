import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import WorkflowStateEventNavButtons from './WorkflowStateDiffNavButtons'
import {
  formatMicrosecondsSinceEpochToTime,
  nanosecondsStringToMicroseconds,
} from '../../../util/duration-utils'
import { PlayIcon } from '@heroicons/react/24/solid'
import { useMemo } from 'react'
import { Link } from 'react-router'
import { useWorkflowDetailRoute } from './workflow-detail-route-context'
import type { WorkflowStoreDiagnosticRequest } from '../../workflow-executions/hooks/use-workflow-store-diagnostic'
import {
  stateEventIdentityKey,
  transitionStateEventIdentity,
} from './state-event-identity'

interface WorkflowDetailStateNavProps {
  traceId: string
  diagnosticRequest: WorkflowStoreDiagnosticRequest
}

export default function WorkflowDetailStateNav(props: WorkflowDetailStateNavProps) {
  const { traceId, diagnosticRequest } = props
  const route = useWorkflowDetailRoute()

  const activeStateEvent = useAppSelector(
    (state: RootState) => state.workflowDetailState.activeStateEvent,
  )

  const storeId = diagnosticRequest.data?.state.store_id ?? null
  const transitions = useMemo(
    () => [...(diagnosticRequest.data?.state.transitions ?? [])].sort(
      (left, right) => left.sequence - right.sequence,
    ),
    [diagnosticRequest.data],
  )
  const activeTransition = transitions.find(
    (transition) => storeId !== null
      && activeStateEvent !== null
      && stateEventIdentityKey(transitionStateEventIdentity(storeId, transition))
      === stateEventIdentityKey(activeStateEvent),
  )
  const statePatchTime = activeStateEvent?.event.timeUnixNano
  const start_micro = statePatchTime
    ? formatMicrosecondsSinceEpochToTime(nanosecondsStringToMicroseconds(statePatchTime))
    : null

  return (
    <div className={'flex items-start justify-between gap-x-2 text-xs text-zinc-500'}>
      {!activeTransition && <div></div>}
      {activeTransition && (
        <div>
          Transition {activeTransition.sequence} &rarr; {activeTransition.action} &rarr;{' '}
          {activeTransition.event_id}{' '}
          <Link to={`/traces/${encodeURIComponent(route.serviceName ?? '')}/${traceId}/${activeTransition.span_id}`}>
            View writer span
          </Link>
        </div>
      )}
      <div className={'font-mono flex items-center gap-x-2'}>
        {activeTransition && <PlayIcon className={'size-4 text-orange-300'} />}
        {start_micro}
        <WorkflowStateEventNavButtons
          traceId={traceId}
          ownerSpanId={diagnosticRequest.data?.workflow_span_id}
          storeId={storeId}
          transitions={transitions}
        />
      </div>
    </div>
  )
}
