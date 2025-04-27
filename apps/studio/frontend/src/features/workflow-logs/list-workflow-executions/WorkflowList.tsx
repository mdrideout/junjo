import { useParams } from 'react-router'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import {
  selectServiceWorkflows,
  selectWorkflowsError,
  selectWorkflowsLoading,
} from '../../otel/store/selectors'
import { RootState } from '../../../root-store/store'
import { useEffect } from 'react'
import { OtelStateActions } from '../../otel/store/slice'
import { useNavigate } from 'react-router'
import { getSpanDurationString } from '../../../util/duration-utils'
import { ExclamationTriangleIcon } from '@heroicons/react/24/solid'

export default function WorkflowsList() {
  const { serviceName } = useParams<{ serviceName: string }>()
  const dispatch = useAppDispatch()
  const navigate = useNavigate()

  const loading = useAppSelector(selectWorkflowsLoading)
  const error = useAppSelector(selectWorkflowsError)
  const workflowSpans = useAppSelector((state: RootState) => selectServiceWorkflows(state, { serviceName }))
  console.log('Workflow spans:', workflowSpans)

  // Fetch the serviceNames
  useEffect(() => {
    console.log('Fetching workflows data...')
    dispatch(OtelStateActions.fetchWorkflowsData({ serviceName }))
  }, [])

  if (loading) {
    return null
  }

  if (error) {
    return <div>Error loading workflow executions.</div>
  }

  return (
    <table className="text-left text-sm">
      <thead>
        <tr>
          <th className={'px-4 py-1'}>Workflow</th>
          <th className={'px-4 py-1'}>Span ID</th>
          <th className={'px-4 py-1'}>Start Time</th>
          <th className={'px-4 py-1'}>Nodes</th>
          <th className={'px-4 py-1'}>Duration</th>
          <th className={'px-4 py-1'}>Exception</th>
        </tr>
      </thead>
      <tbody>
        {workflowSpans.map((item) => {
          const nodeCount = item.attributes_json['junjo.workflow.node.count'] ?? null

          // Make date human readable
          const start = new Date(item.start_time)
          const startString = start.toLocaleString()

          // Duration String
          const durationString = getSpanDurationString(item.start_time, item.end_time)

          // Exceptions
          const hasExceptions = item.events_json.some((event) => {
            return event.attributes && event.attributes['exception.type'] !== undefined
          })

          return (
            <tr
              key={item.span_id}
              className={
                'last-of-type:border-0 border-b border-zinc-200 dark:border-zinc-600 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer'
              }
              onClick={() => navigate(`${item.span_id}`)}
            >
              <td className={'px-4 py-1.5'}>{item.name}</td>
              <td className={'px-4 py-1.5 font-mono'}>{item.span_id}</td>
              <td className={'px-4 py-1.5 font-mono'}>{startString}</td>
              <td className={'px-4 py-1.5 text-right font-mono'}>{nodeCount}</td>
              <td className={'px-4 py-1.5 text-right font-mono'}>{durationString}</td>
              <td className={'px-4 py-1.5'}>
                {hasExceptions && (
                  <ExclamationTriangleIcon className={'size-5 m-auto text-red-700 dark:text-red-300'} />
                )}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
