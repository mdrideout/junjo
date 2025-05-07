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
import WorkflowListRow from './WorkflowListItem'

export default function WorkflowsList() {
  const { serviceName } = useParams<{ serviceName: string }>()
  const dispatch = useAppDispatch()
  const navigate = useNavigate()

  const loading = useAppSelector(selectWorkflowsLoading)
  const error = useAppSelector(selectWorkflowsError)
  const workflowSpans = useAppSelector((state: RootState) => selectServiceWorkflows(state, { serviceName }))

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
        {workflowSpans.map((item) => (
          <WorkflowListRow key={`list-row-${item.span_id}`} workflowSpan={item} />
        ))}
      </tbody>
    </table>
  )
}
