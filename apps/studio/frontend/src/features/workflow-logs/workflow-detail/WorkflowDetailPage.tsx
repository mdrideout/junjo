import { Link, useParams } from 'react-router'
import ErrorPage from '../../../components/errors/ErrorPage'
import { useEffect, useState } from 'react'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { selectWorkflowsError, selectWorkflowsLoading, selectWorkflowSpan } from '../../otel/store/selectors'
import { RootState } from '../../../root-store/store'
import { OtelStateActions } from '../../otel/store/slice'
import { getSpanDurationString } from '../../../util/duration-utils'
import WorkflowDetailNavButtons from './WorkflowDetailNavButtons'
import WorkflowDetailStateDiff from './WorkflowDetailStateDiff'
import { JunjoGraph } from '../../../junjo-graph/junjo-graph'
import NestedWorkflowSpans from '../node-logs/NestedWorkflowSpans'
import RenderJunjoGraphMermaid from '../../../mermaidjs/RenderJunjoGraphMermaid'
import { nanoid } from '@reduxjs/toolkit'
import { Switch } from 'radix-ui'

export default function WorkflowDetailPage() {
  const { serviceName, spanID } = useParams()
  const dispatch = useAppDispatch()
  const [mermaidEdgeLabels, setMermaidEdgeLabels] = useState<boolean>(false)

  const loading = useAppSelector(selectWorkflowsLoading)
  const error = useAppSelector(selectWorkflowsError)
  const span = useAppSelector((state: RootState) => selectWorkflowSpan(state, { serviceName, spanID }))

  // Fetch the serviceNames
  useEffect(() => {
    console.log('Fetching workflows data...')
    dispatch(OtelStateActions.fetchWorkflowsData({ serviceName }))
  }, [])

  if (loading) return null

  if (error) {
    return <ErrorPage title={'Error'} message={`Error loading workflow span`} />
  }

  if (!spanID || !serviceName || !span) {
    return <div>No logs found.</div>
  }

  // Human readable start ingest time
  const date = new Date(span.start_time)
  const readableStart = date.toLocaleString()

  // Parse duration
  const durationString = getSpanDurationString(span.start_time, span.end_time)

  // Parse mermaid flow string
  const mermaidFlowString = JunjoGraph.fromJson(span.junjo_wf_graph_structure).toMermaid(mermaidEdgeLabels)
  const mermaidUniqueId = nanoid()

  return (
    <div className={'p-5 flex flex-col h-dvh'}>
      <div className={'flex gap-x-3 px-2 items-center justify-between'}>
        <div>
          <div className={'mb-1 flex gap-x-3 font-bold'}>
            <Link to={'/logs'} className={'hover:underline'}>
              Logs
            </Link>
            <div>&rarr;</div>
            <Link to={`/logs/${serviceName}`} className={'hover:underline'}>
              {serviceName}
            </Link>
            <div>&rarr;</div>
            <div>
              {span.name} <span className={'text-xs font-normal'}>({spanID})</span>
            </div>
          </div>
          <div className={'text-zinc-400 text-xs'}>
            {readableStart} &mdash; {durationString}
          </div>
        </div>
        <WorkflowDetailNavButtons serviceName={serviceName} workflowSpanID={spanID} />
      </div>

      <hr className={'my-6'} />

      <div className={`w-full shrink-0 pb-3 mb-3 h-64 overflow-scroll`}>
        <div className={'absolute'}>
          <div className="flex items-center">
            <label className={'pr-3 text-xs leading-none'} htmlFor="airplane-mode">
              Edge labels
            </label>
            <Switch.Root
              checked={mermaidEdgeLabels}
              onCheckedChange={setMermaidEdgeLabels}
              className="relative h-[14px] w-[28px] border-0 cursor-default rounded-full outline-none bg-zinc-200 data-[state=checked]:bg-zinc-300"
              id="edge-label-switch"
              // stylelint-disable-next-line property-no-vendor-prefix
              style={{ '-webkit-tap-highlight-color': 'rgba(0, 0, 0, 0)' }}
            >
              <Switch.Thumb className="block size-[14px] bg-zinc-700 translate-x-[1px] rounded-full transition-transform duration-100 will-change-transform data-[state=checked]:translate-x-[13px]" />
            </Switch.Root>
          </div>
        </div>
        <RenderJunjoGraphMermaid
          mermaidFlowString={mermaidFlowString}
          mermaidUniqueId={mermaidUniqueId}
          serviceName={serviceName}
          workflowSpanID={spanID}
        />
      </div>
      <div className={'grow w-full flex gap-x-10 justify-between overflow-hidden'}>
        <NestedWorkflowSpans serviceName={serviceName} workflowSpanID={spanID} />
        <WorkflowDetailStateDiff
          workflowStateStart={span.junjo_wf_state_start}
          workflowStateEnd={span.junjo_wf_state_end}
          workflowSpanID={spanID}
          serviceName={serviceName}
        />
      </div>
    </div>
  )
}
