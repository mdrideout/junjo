import { useParams } from 'react-router'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import { selectServiceWorkflows, selectWorkflowsError, selectWorkflowsLoading } from '../../otel/store/selectors'
import { RootState } from '../../../root-store/store'
import { useEffect } from 'react'
import { OtelStateActions } from '../../otel/store/slice'

export default function WorkflowsList() {
  const { serviceName } = useParams<{ serviceName: string }>()
  const dispatch = useAppDispatch()
  // const navigate = useNavigate()

  const loading = useAppSelector(selectWorkflowsLoading)
  const error = useAppSelector(selectWorkflowsError)
  const workflowSpans = useAppSelector((state: RootState) => selectServiceWorkflows(state, { serviceName })) ?? []

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
          <th className={'px-4 py-1'}>Execution ID</th>
          <th className={'px-4 py-1'}>Created At</th>
        </tr>
      </thead>
      <tbody>
        {workflowSpans.map((item) => {
          // Make date human readable
          const date = new Date(item.start_time)
          const dateString = date.toLocaleString()

          return (
            <tr
              key={item.span_id}
              className={
                'last-of-type:border-0 border-b border-zinc-200 dark:border-zinc-600 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer'
              }
              onClick={() => console.log('Navigate to the workflow details.')}
            >
              <td className={'px-4 py-1.5'}>{item.name}</td>
              <td className={'px-4 py-1.5'}>{item.junjo_id}</td>
              <td className={'px-4 py-1.5'}>{dateString}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
