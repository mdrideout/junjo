import { WorkflowLog } from '../schemas'
import { Link, useParams } from 'react-router'
import ErrorPage from '../../components/errors/ErrorPage'
import WorkflowStructure from './WorkflowStructure'
import { decodeBase64Json } from '../../util/decode-base64-json'
import { useQuery } from '@tanstack/react-query'
import { fetchWorkflowLogs } from '../fetch/fetch-workflow-logs'
import JsonView from '@uiw/react-json-view'
import { lightTheme } from '@uiw/react-json-view/light'

export default function WorkflowLogPage() {
  const { ExecID } = useParams()

  // useQuery<DataType, ErrorType>
  const {
    data: workflowLogs,
    isLoading,
    isError,
    error,
  } = useQuery<WorkflowLog[], Error>({
    queryKey: ['workflowLogs', ExecID],
    queryFn: () => fetchWorkflowLogs(ExecID!),
    enabled: !!ExecID,
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

  // console.log('Workflow logs: ', workflowLogs)
  // const jsonLogs0 = decodeBase64Json(workflowLogs[0].State)
  // const jsonLogs1 = decodeBase64Json(workflowLogs[1].State)

  // const diffed = diff(jsonLogs0, jsonLogs1)
  // console.log('Diff: ', diffed)

  return (
    <div className={'p-5'}>
      <div className={'px-2'}>
        <div className={'mb-1 flex gap-x-3 font-bold'}>
          <Link to={'/logs'} className={'hover:underline'}>
            Logs
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
            const displayState = JSON.stringify(decodeBase64Json(log.State), null, 2)

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
                <JsonView
                  value={decodeBase64Json(log.State)}
                  collapsed={3}
                  shouldExpandNodeInitially={(isExpanded, { value, keys, level }) => {
                    // Collapse arrays more than 1 level deep (not root arrays)
                    const isArray = Array.isArray(value)
                    if (isArray && level > 1) {
                      const arrayLength = Object.keys(value).length

                      // Only hide if the array length is greater than 1
                      if (arrayLength > 1) {
                        return true
                      }
                    }

                    return isExpanded
                  }}
                  style={lightTheme}
                />
                {/* <div>
                  <pre>{displayState}</pre>
                </div> */}
              </div>
            )
          })}
        </div>
        <div className="h-10"></div>
        <strong>Graph Structure:</strong>
        <WorkflowStructure ExecID={ExecID} />
      </div>
    </div>
  )
}
