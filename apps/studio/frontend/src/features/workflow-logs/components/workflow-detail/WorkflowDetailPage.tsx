import { Link, useParams } from 'react-router'
import ErrorPage from '../../../../components/errors/ErrorPage'
import WorkflowStructure from './WorkflowStructure'
import WorkflowLogStateDiff from './WorkflowDetailStateDiff'
import LogPageNavButtons from './LogPageNavButtons'
import { useFetchWorkflowLogs } from '../../hooks/useFetchWorkflowLogs'

export default function WorkflowDetailPage() {
  const { AppName, ExecID } = useParams()

  const { workflowLogs, isLoading, error } = useFetchWorkflowLogs(ExecID || '')

  if (isLoading) return null

  if (error) {
    return <ErrorPage title={'Error'} message={`Error loading workflow logs: ${error.message}`} />
  }

  if (!ExecID || !workflowLogs || workflowLogs.length === 0) {
    return <div>No logs found.</div>
  }

  // Human readable start ingest time
  const date = new Date(workflowLogs[0]?.IngestionTime)
  const readableStart = date.toLocaleString()

  // Parse duration
  const durationNano = workflowLogs[1]?.EventTimeNano - workflowLogs[0]?.EventTimeNano
  const durationMs = durationNano / 1e6
  const durationMsRounded = Math.round(durationMs * 100) / 100

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
              <Link to={`/logs/${AppName}`} className={'hover:underline'}>
                {AppName}
              </Link>
              <div>&rarr;</div>
              <div>{ExecID}</div>
            </div>
            <div className={'text-zinc-400 text-xs'}>
              {readableStart} &mdash; {durationMsRounded} ms
            </div>
          </div>
          <LogPageNavButtons ExecID={ExecID} />
        </div>
      </div>
      <hr className={'my-6'} />
      {workflowLogs.length === 0 && <p>No logs found for this workflow.</p>}
      <WorkflowStructure ExecID={ExecID} />
      <WorkflowLogStateDiff startLog={workflowLogs[0]} endLog={workflowLogs[1]} />
    </div>
  )
}
