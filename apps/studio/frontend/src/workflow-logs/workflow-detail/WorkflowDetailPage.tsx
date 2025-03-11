import { WorkflowLog } from '../schemas'
import { Link, useParams } from 'react-router'
import ErrorPage from '../../components/errors/ErrorPage'
import WorkflowStructure from './WorkflowStructure'
import { decodeBase64Json } from '../../util/decode-base64-json'
import { useQuery } from '@tanstack/react-query'
import { fetchWorkflowLogs } from '../fetch/fetch-workflow-logs'
import WorkflowLogStateDiff from './WorkflowDetailStateDiff'
import LogPageNavButtons from './LogPageNavButtons'

export default function WorkflowDetailPage() {
  const { AppName, ExecID } = useParams()

  // useQuery<DataType, ErrorType>
  const {
    data: workflowLogs,
    isLoading,
    isError,
    error,
  } = useQuery<WorkflowLog[], Error>({
    queryKey: ['workflowLogs', ExecID],
    enabled: !!ExecID,
    queryFn: () => fetchWorkflowLogs(ExecID!),
    staleTime: 1000 * 60 * 5, // 5 minutes
  })

  if (isLoading) {
    return null
  }

  if (isError) {
    console.log('Error', error)
    return <ErrorPage title={'404: Not Found'} message={`No workflow logs found for id: ${ExecID}`} />
  }

  if (!ExecID || !workflowLogs || workflowLogs.length === 0) {
    return <div>No metadata found.</div>
  }

  // Human readable start ingest time
  const date = new Date(workflowLogs[0]?.IngestionTime)
  const readableStart = date.toLocaleString()

  // Parse duration
  const durationNano = workflowLogs[1]?.EventTimeNano - workflowLogs[0]?.EventTimeNano
  const durationMs = durationNano / 1e6
  const durationMsRounded = Math.round(durationMs * 100) / 100

  const startLogs = decodeBase64Json(workflowLogs[0].State)
  const endLogs = decodeBase64Json(workflowLogs[1].State)

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
      <WorkflowLogStateDiff jsonLogs0={startLogs} jsonLogs1={endLogs} />
    </div>
  )
}
