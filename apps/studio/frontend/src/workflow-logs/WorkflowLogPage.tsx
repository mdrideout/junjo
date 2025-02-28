import { useEffect, useState } from 'react'
import { WorkflowLog } from './schemas'
import { fetchWorkflowLogs } from './fetch/fetch-workflow-logs'
import { Link, useParams } from 'react-router'
import ErrorPage from '../components/errors/ErrorPage'

export default function WorkflowLogPage() {
  const { ExecID } = useParams()
  const [workflowLogs, setWorkflowLogs] = useState<WorkflowLog[]>([])

  useEffect(() => {
    if (!ExecID) return

    const run = async () => {
      try {
        const logs = await fetchWorkflowLogs(ExecID)
        setWorkflowLogs(logs)
      } catch (error) {
        console.error('Failed to fetch workflow logs:', error)
      } finally {
        // TODO
      }
    }

    run()
  }, [])

  if (!ExecID) {
    return <ErrorPage title={'404: Not Found'} message={'No workflows found with this execution id.'} />
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
        <div className={'mb-1 flex gap-x-3'}>
          <Link to={'/logs'} className={'hover:underline'}>
            logs
          </Link>{' '}
          <div>&rarr;</div>
          <div>{ExecID}</div>
        </div>
        <div className={'text-zinc-400 text-xs'}>
          {readableStart} &mdash; {durationMsRounded} ms
        </div>
      </div>
      <hr className={'my-6'} />
      <div className={'px-2'}>
        <div className="flex gap-10">
          {workflowLogs.length === 0 && <p>No logs found for this workflow.</p>}
          {workflowLogs.map((log) => {
            // Decode the base64 encoded state into stringified json,
            // then format the JSON string with 2 spaces for indentation
            const displayState = JSON.stringify(JSON.parse(atob(log.State)), null, 2)

            return (
              <div key={log.ID} className={''}>
                {/* <p>
                  <strong>Log ID:</strong> {log.ID}
                </p>
                <p>
                  <strong>Execution ID:</strong> {log.ExecID}
                </p>
                <p>
                  <strong>Nano time number:</strong> {log.EventTimeNano}
                </p>
                <p>
                  <strong>Ingest time:</strong> {log.IngestionTime}
                </p> */}
                <p>
                  <strong>{log.Type}</strong>
                </p>
                <div>
                  <pre>{displayState}</pre>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
