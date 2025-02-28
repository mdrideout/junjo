import WorkflowList from './WorkflowList'

/**
 * Workflow List Page
 *
 * Lists the workflow runs that have taken place.
 * @returns
 */
export default function WorkflowListPage() {
  return (
    <div className={'p-5'}>
      <h1>workflow logs</h1>
      <div className="h-2"></div>
      <WorkflowList />
    </div>
    // <>
    //   <div className={'p-5'}>
    //     <h1>LOGS</h1>
    //     <div className="flex gap-5">
    //       {workflowList.map((log) => {
    //         // Decode the base64 encoded state into stringified json,
    //         // then format the JSON string with 2 spaces for indentation
    //         const displayState = JSON.stringify(JSON.parse(atob(log.State)), null, 2)

    //         return (
    //           <div key={log.ID} className={''}>
    //             <p>
    //               <strong>Log ID:</strong> {log.ID}
    //             </p>
    //             <p>
    //               <strong>Execution ID:</strong> {log.ExecID}
    //             </p>
    //             <p>
    //               <strong>Nano time number:</strong> {log.EventTimeNano}
    //             </p>
    //             <p>
    //               <strong>Ingest time:</strong> {log.IngestionTime}
    //             </p>
    //             <p>
    //               <strong>Type:</strong> {log.Type}
    //             </p>
    //             <div>
    //               <strong>State:</strong> <pre>{displayState}</pre>
    //             </div>
    //           </div>
    //         )
    //       })}
    //     </div>
    //   </div>
    // </>
  )
}
