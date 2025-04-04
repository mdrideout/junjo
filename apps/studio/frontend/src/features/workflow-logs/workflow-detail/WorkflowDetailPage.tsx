import { Link, useParams } from 'react-router'
import ErrorPage from '../../../components/errors/ErrorPage'
import { useEffect } from 'react'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { selectWorkflowsError, selectWorkflowsLoading, selectWorkflowSpan } from '../../otel/store/selectors'
import { RootState } from '../../../root-store/store'
import { OtelStateActions } from '../../otel/store/slice'
import { getSpanDurationString } from '../../../util/duration-utils'
import WorkflowDetailNavButtons from './WorkflowDetailNavButtons'
import WorkflowStructure from './WorkflowStructure'
import NodeLogsList from '../node-logs/NodeLogsList'
import WorkflowDetailStateDiff from './WorkflowDetailStateDiff'
import { JunjoGraph } from '../../../junjo-graph/junjo-graph'
import { ActiveNodeProvider } from './ActiveNodeContext'
import NestedWorkflowSpans from '../node-logs/NestedWorkflowSpans'

export default function WorkflowDetailPage() {
  const { serviceName, spanID } = useParams()
  const dispatch = useAppDispatch()

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

  console.log('Rendering workflow: ', span)

  return (
    <div className={'p-5'}>
      <div className={'px-2'}>
        <div className={'flex gap-x-3 items-center justify-between'}>
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
      </div>
      <hr className={'my-6'} />
      <WorkflowStructure graph={JunjoGraph.fromJson(span.junjo_wf_graph_structure)} />
      <ActiveNodeProvider>
        <div className={'w-full flex gap-x-14 justify-between'}>
          <NestedWorkflowSpans serviceName={serviceName} workflowSpanID={spanID} />
          {/* <NodeLogsList workflowSpanID={spanID} serviceName={serviceName} /> */}
          <WorkflowDetailStateDiff
            workflowStateStart={span.junjo_wf_state_start}
            workflowStateEnd={span.junjo_wf_state_end}
            workflowSpanID={spanID}
            serviceName={serviceName}
          />
        </div>
      </ActiveNodeProvider>
    </div>
  )
}
