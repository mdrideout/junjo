import { Link, useParams } from 'react-router'
import ErrorPage from '../../../components/errors/ErrorPage'
import { useEffect } from 'react'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { selectWorkflowsError, selectWorkflowsLoading, selectWorkflowSpan } from '../../otel/store/selectors'
import { RootState } from '../../../root-store/store'
import { OtelStateActions } from '../../otel/store/slice'
import { getSpanDurationString } from '../../../util/duration-utils'
import LogPageNavButtons from './LogPageNavButtons'
import WorkflowStructure from './WorkflowStructure'
import NodeLogsList from '../node-logs/NodeLogsList'
import WorkflowDetailStateDiff from './WorkflowDetailStateDiff'

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
              <div>{spanID}</div>
            </div>
            <div className={'text-zinc-400 text-xs'}>
              {readableStart} &mdash; {durationString}
            </div>
          </div>
          <LogPageNavButtons spanID={spanID} />
        </div>
      </div>
      <hr className={'my-6'} />
      <WorkflowStructure spanID={spanID} />
      <div className={'flex gap-x-5 justify-between'}>
        <NodeLogsList spanID={spanID} />
        <WorkflowDetailStateDiff stateStart={span.junjo_wf_state_start} stateEnd={span.junjo_wf_state_end} />
      </div>
    </div>
  )
}
