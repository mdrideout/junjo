import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import WorkflowStateEventNavButtons from './WorkflowStateDiffNavButtons'
import {
  formatMicrosecondsSinceEpochToTime,
  nanosecondsStringToMicroseconds,
} from '../../../util/duration-utils'
import { PlayIcon } from '@heroicons/react/24/solid'
import { useMemo } from 'react'
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
          {activeTransition.event_id}
        </div>
      )}
      <div className={'font-mono flex items-center gap-x-2'}>
        {activeTransition && <PlayIcon className={'size-4 text-orange-300'} />}
        {start_micro}
        <WorkflowStateEventNavButtons
          traceId={traceId}
          storeId={storeId}
          transitions={transitions}
        />
      </div>
    </div>
  )
}
