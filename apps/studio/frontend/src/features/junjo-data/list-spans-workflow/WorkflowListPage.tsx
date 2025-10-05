import { Link, useParams } from 'react-router'
import WorkflowList from './WorkflowList'

/**
 * Workflow List Page
 *
 * Lists the workflow runs that have taken place.
 * @returns
 */
export default function WorkflowListPage() {
  const { serviceName } = useParams()

  if (!serviceName) {
    return <div>Service name is required</div>
  }

  // Human readable start ingest time
  const date = new Date()
  const readableDate = date.toLocaleString()

  return (
    <div className={'px-2 py-3 flex flex-col h-dvh overflow-hidden'}>
      <div className={'px-2'}>
        <div className={'mb-1 flex gap-x-3 font-bold'}>
          <Link to={'/logs'} className={'hover:underline'}>
            Logs
          </Link>
          <div>&rarr;</div>
          <div>{serviceName}</div>
          <div>&rarr;</div>
          <div>Workflow Executions</div>
        </div>
        <div className={'text-zinc-400 text-xs'}>{readableDate}</div>
      </div>
      <hr className={'my-6'} />
      <div className={'grow overflow-scroll'}>
        <WorkflowList serviceName={serviceName} />
      </div>
    </div>
  )
}
