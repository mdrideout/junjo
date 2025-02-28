import { useEffect } from 'react'
import { WorkflowMetadatum } from './schemas'
import { fetchWorkflowMetadataList } from './fetch/fetch-workflow-metadata'
import { useNavigate } from 'react-router'
import { useMetadataStore } from './store/workflow_metadata_store'

export default function WorkflowsList() {
  const navigate = useNavigate()

  const { metadata, setMetadata } = useMetadataStore((state) => ({
    metadata: state.metadata,
    setMetadata: state.setMetadata,
  }))

  useEffect(() => {
    const run = async () => {
      try {
        const list = await fetchWorkflowMetadataList()
        setMetadata(list)
      } catch (error) {
        console.error('Failed to fetch workflow logs:', error)
      } finally {
        // TODO
      }
    }

    run()
  }, [])

  const workflowMetadataList = Object.values(metadata) as WorkflowMetadatum[]

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
        {workflowMetadataList.map((item) => {
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
