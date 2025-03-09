import { useQuery } from '@tanstack/react-query'
import { WorkflowMetadatum } from './schemas'
import { useNavigate } from 'react-router'
import { fetchWorkflowMetadataList } from './fetch/fetch-workflow-metadata'

export default function WorkflowsList() {
  const navigate = useNavigate()

  const {
    data: metadataList,
    isLoading,
    isError,
    error,
  } = useQuery<WorkflowMetadatum[], Error>({
    queryKey: ['workflowMetadataList'],
    queryFn: fetchWorkflowMetadataList,
    select: (data) => data,
    // refetchInterval: 1000 * 3,
  })

  if (isLoading) {
    return <div>Loading metadata list...</div>
  }

  if (isError) {
    return <div>Error: {error.message}</div>
  }

  if (!metadataList) {
    return <div>No metadata found.</div>
  }

  return (
    <table className="text-left">
      <thead>
        <tr>
          <th className={'px-4 py-1'}>Execution ID</th>
          <th className={'px-4 py-1'}>Name</th>
          <th className={'px-4 py-1'}>Created At</th>
        </tr>
      </thead>
      <tbody>
        {metadataList.map((item) => {
          // Make date human readable
          const date = new Date(item.CreatedAt)
          item.CreatedAt = date.toLocaleString()

          return (
            <tr
              key={item.ID}
              className={
                'last-of-type:border-0 border-b border-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer'
              }
              onClick={() => navigate(`${item.ExecID}`)}
            >
              <td className={'px-4 py-1.5'}>{item.ExecID}</td>
              <td className={'px-4 py-1.5'}>{item.Name}</td>
              <td className={'px-4 py-1.5'}>{item.CreatedAt}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
