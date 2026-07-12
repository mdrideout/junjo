import { useAppSelector } from '../../../root-store/hooks'
import { RootState } from '../../../root-store/store'
import WorkflowStateEventNavButtons from './WorkflowStateDiffNavButtons'
import { formatMicrosecondsSinceEpochToTime } from '../../../util/duration-utils'
import { PlayIcon } from '@heroicons/react/24/solid'

interface WorkflowDetailStateNavProps {
  traceId: string
  workflowSpanId: string
}

export default function WorkflowDetailStateNav(props: WorkflowDetailStateNavProps) {
  const { traceId, workflowSpanId } = props

  const activeSetStateEvent = useAppSelector(
    (state: RootState) => state.workflowDetailState.activeSetStateEvent,
  )

  const atts = activeSetStateEvent?.attributes
  const statePatchTime = activeSetStateEvent?.timeUnixNano
  const start_micro = statePatchTime
    ? formatMicrosecondsSinceEpochToTime(activeSetStateEvent?.timeUnixNano / 1000)
    : null

  return (
    <div className={'flex items-start justify-between gap-x-2 text-xs text-zinc-500'}>
      {!atts && <div></div>}
      {atts && (
        <div>
          {atts['junjo.store.name']} &rarr; {atts['junjo.store.action']} &rarr; {atts.id}
        </div>
      )}
      <div className={'font-mono flex items-center gap-x-2'}>
        {atts && <PlayIcon className={'size-4 text-orange-300'} />}
        {start_micro}
        <WorkflowStateEventNavButtons traceId={traceId} workflowSpanId={workflowSpanId} />
      </div>
    </div>
  )
}
