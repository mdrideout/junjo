import { Link, useParams } from 'react-router'
import WorkflowList from './WorkflowList'

/**
 * Workflow List Page
 *
 * Lists the workflow runs that have taken place.
 * @returns
 */
export default function WorkflowListPage() {
  const { AppName } = useParams()

  // Human readable start ingest time
  const date = new Date()
  const readableDate = date.toLocaleString()

  return (
    <div className={'p-5'}>
      <div className={'px-2'}>
        <div className={'mb-1 flex gap-x-3 font-bold'}>
          <Link to={'/logs'} className={'hover:underline'}>
            Logs
          </Link>
          <div>&rarr;</div>
          <div>{AppName}</div>
        </div>
        <div className={'text-zinc-400 text-xs'}>{readableDate}</div>
      </div>
      <hr className={'my-6'} />
      <WorkflowList />
    </div>
  )
}
