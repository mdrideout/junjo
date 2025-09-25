import { Link, useParams } from 'react-router'
import ErrorPage from '../../../components/errors/ErrorPage'
import { useEffect, useState } from 'react'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { selectSpanById } from '../../traces/store/selectors'
import { RootState } from '../../../root-store/store'
import { getSpanDurationString } from '../../../util/duration-utils'
import WorkflowDetailNavButtons from './WorkflowDetailNavButtons'
import WorkflowDetailStateDiff from './WorkflowDetailStateDiff'
import { Switch } from 'radix-ui'
import RenderJunjoGraphList from '../../../mermaidjs/RenderJunjoGraphList'
import TabbedSpanLists from '../span-lists/TabbedSpanLists'
import WorkflowDetailStateNav from './WorkflowDetailStateNav'
import { TracesStateActions } from '../../traces/store/slice'

export default function WorkflowDetailPage() {
  const { serviceName, traceId, workflowSpanId } = useParams()
  const dispatch = useAppDispatch()
  const [mermaidEdgeLabels, setMermaidEdgeLabels] = useState<boolean>(false)

  const loading = useAppSelector((state: RootState) => state.tracesState.loading)
  const error = useAppSelector((state: RootState) => state.tracesState.error)
  const span = useAppSelector((state: RootState) =>
    selectSpanById(state, {
      traceId: traceId,
      spanId: workflowSpanId,
    }),
  )

  // Data fetching
  useEffect(() => {
    // If the span does not yet exist in state, fetch it
    if (!span) {
      dispatch(TracesStateActions.fetchSpansByTraceId({ traceId }))
    }
  }, [dispatch, span])

  if (loading) return null

  if (error) {
    return <ErrorPage title={'Error'} message={`Error loading workflow span`} />
  }

  // No data rendering
  if (!serviceName || !traceId || !workflowSpanId || !span) {
    return <div className={'p-2'}>No logs found.</div>
  }

  // Human readable start ingest time
  const date = new Date(span.start_time)
  const readableStart = date.toLocaleString()

  // Parse duration
  const durationString = getSpanDurationString(span.start_time, span.end_time)

  return (
    <div className={'px-2 py-3 flex flex-col h-dvh overflow-hidden'}>
      <div className={'flex gap-x-3 px-2 items-center justify-between'}>
        <div>
          <div className={'mb-1 flex gap-x-3 font-bold'}>
            <Link to={'/logs'} className={'hover:underline'}>
              Logs
            </Link>
            <div>&rarr;</div>
            <div>{serviceName}</div>
            <div>&rarr;</div>
            <Link to={`/logs/${serviceName}`} className={'hover:underline'}>
              Workflow Executions
            </Link>
            <div>&rarr;</div>
            <div>
              {span.name} <span className={'text-xs font-normal'}>({workflowSpanId})</span>
            </div>
          </div>
          <div className={'text-zinc-400 text-xs'}>
            {readableStart} &mdash; {durationString}
          </div>
        </div>
        <WorkflowDetailNavButtons serviceName={serviceName} workflowSpanId={workflowSpanId} />
      </div>

      <hr className={'my-4'} />

      <div className={`w-full shrink-0 pb-3 h-80 overflow-scroll shadow-md p-3 bg-zinc-50 dark:bg-zinc-800`}>
        <div className={'mb-2'}>
          <div className="flex items-center">
            <label className={'pr-3 text-xs leading-none'} htmlFor="airplane-mode">
              Edge labels
            </label>
            <Switch.Root
              checked={mermaidEdgeLabels}
              onCheckedChange={setMermaidEdgeLabels}
              className="relative h-[14px] w-[28px] border-0 cursor-default rounded-full outline-none bg-zinc-200 data-[state=checked]:bg-zinc-300"
              id="edge-label-switch"
            >
              <Switch.Thumb className="block size-[14px] bg-zinc-700 translate-x-[1px] rounded-full transition-transform duration-100 will-change-transform data-[state=checked]:translate-x-[13px]" />
            </Switch.Root>
          </div>
        </div>
        <RenderJunjoGraphList
          workflowSpanId={workflowSpanId}
          showEdgeLabels={mermaidEdgeLabels}
          traceId={traceId}
        />
      </div>
      <div className={'pt-2 px-2 pb-2'}>
        <WorkflowDetailStateNav serviceName={serviceName} workflowSpanId={workflowSpanId} />
      </div>

      <div className={'grow w-full flex gap-x-4 justify-between overflow-hidden'}>
        <TabbedSpanLists serviceName={serviceName} workflowSpanId={workflowSpanId} />
        <WorkflowDetailStateDiff defaultWorkflowSpan={span} />
      </div>
    </div>
  )
}
