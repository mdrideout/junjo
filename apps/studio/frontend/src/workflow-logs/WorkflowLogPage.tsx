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

  return (
    <div className={'p-5'}>
      <div className={'mb-3 flex gap-x-3'}>
        <Link to={'/logs'} className={'hover:underline'}>
          logs
        </Link>{' '}
        <div>&gt;</div> <div>{ExecID}</div>
      </div>
      <hr className={'my-5'} />
      <div className={''}>
        <div className="flex gap-5">
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
                </p> */}
                <p>
                  <strong>Nano time number:</strong> {log.EventTimeNano}
                </p>
                <p>
                  <strong>Ingest time:</strong> {log.IngestionTime}
                </p>
                <p>
                  <strong>Type:</strong> {log.Type}
                </p>
                <div>
                  <strong>State:</strong> <pre>{displayState}</pre>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
