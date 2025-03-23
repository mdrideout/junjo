interface NodeLogsListProps {
  spanID: string
}

export default function NodeLogsList(props: NodeLogsListProps) {
  const { spanID } = props

  const loading = false
  const error = false
  const nodeLogs: null | [] = []

  if (loading || !nodeLogs) return null

  if (error) {
    return <div>Error loading node logs</div>
  }

  if (!nodeLogs || nodeLogs.length === 0) {
    return <div>No node logs found for this execution.</div>
  }

  return <div>Render the node logs list here for {spanID}</div>

  // return (
  //   <div>
  //     <table className="text-left text-sm">
  //       <thead>
  //         <tr>
  //           <th className={'px-4 py-1'}>ID</th>
  //           <th className={'px-4 py-1'}>Time Nano</th>
  //           <th className={'px-4 py-1'}>Type</th>
  //         </tr>
  //       </thead>
  //       <tbody>
  //         {nodeLogs.map((item) => {
  //           // Make date human readable
  //           // const date = new Date(item.IngestionTime)
  //           // const dateString = date.toLocaleString()
  //           return (
  //             <tr
  //               key={item.ID}
  //               className={
  //                 'last-of-type:border-0 border-b border-zinc-200 dark:border-zinc-600 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer'
  //               }
  //               onClick={() => console.log('DO SOMETHING.')}
  //             >
  //               <td className={'px-4 py-1.5'}>{item.ID}</td>
  //               <td className={'px-4 py-1.5'}>{item.EventTimeNano}</td>
  //               <td className={'px-4 py-1.5'}>{item.Type}</td>
  //             </tr>
  //           )
  //         })}
  //       </tbody>
  //     </table>
  //   </div>
  // )
}
