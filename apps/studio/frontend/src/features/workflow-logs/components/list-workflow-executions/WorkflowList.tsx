import { useNavigate, useParams } from 'react-router'
import { useFetchWorkflowExecutions } from '../../hooks/useFetchWorkflowExecutions'

export default function WorkflowsList() {
  const { AppName } = useParams<{ AppName: string }>()
  const navigate = useNavigate()
  const { workflowExecutions, isLoading, error } = useFetchWorkflowExecutions(AppName)

  if (isLoading) {
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
        {workflowExecutions.map((item) => {
          // Make date human readable
          const date = new Date(item.CreatedAt)
          const dateString = date.toLocaleString()

          return (
            <tr
              key={item.ID}
              className={
                'last-of-type:border-0 border-b border-zinc-200 dark:border-zinc-600 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer'
              }
              onClick={() => navigate(`${item.ExecID}`)}
            >
              <td className={'px-4 py-1.5'}>{item.WorkflowName}</td>
              <td className={'px-4 py-1.5'}>{item.ExecID}</td>
              <td className={'px-4 py-1.5'}>{dateString}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
