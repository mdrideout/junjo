import { useEffect, useState } from 'react'
import { WorkflowLog } from '../schemas'
import { fetchWorkflowLogs } from '../fetch/fetch-workflow-logs'
import { fetchWorkflowMetadata } from '../fetch/fetch-workflow-metadata'

export default function WorkflowsPage() {
  // Fetch workflow logs
  const [workflowLogs, setWorkflowLogs] = useState<WorkflowLog[]>([])

  useEffect(() => {
    const run = async () => {
      try {
        const metadata = await fetchWorkflowMetadata()
        const logs = await fetchWorkflowLogs('msjAutbVsovocbHU7Ozdh')
        setWorkflowLogs(logs)
      } catch (error) {
        console.error('Failed to fetch workflow logs:', error)
      } finally {
        // TODO
      }
    }

    run()
  }, [])

  return (
    <>
      <div className={'p-5'}>
        <h1>LOGS</h1>
        <div className="flex gap-5">
          {workflowLogs.map((log) => {
            // Decode the base64 encoded state into stringified json,
            // then format the JSON string with 2 spaces for indentation
            const displayState = JSON.stringify(JSON.parse(atob(log.State)), null, 2)

            return (
              <div key={log.ID} className={''}>
                <p>
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
    </>
  )
}
