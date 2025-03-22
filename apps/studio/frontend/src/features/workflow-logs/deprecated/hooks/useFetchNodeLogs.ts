// // LEFT OFF: See gemini chat for new hook / slice / and component implementation
// import { useEffect, useState } from 'react'
// import { fetchNodeLogs } from '../fetch/fetch-node-logs'
// import { LogStateActions, selectNodeLogs } from '../store/slice'
// import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'

// export const useFetchNodeLogs = (ExecID: string) => {
//   const dispatch = useAppDispatch()
//   const nodeLogs = useAppSelector((state) => selectNodeLogs(state, ExecID))
//   const isLoading = nodeLogs === undefined && ExecID !== ''
//   const [error, setError] = useState<Error | null>(null)

//   useEffect(() => {
//     const fetchAndStoreNodeLogs = async () => {
//       setError(null)
//       if (ExecID === '') return

//       try {
//         const logs = await fetchNodeLogs(ExecID)
//         dispatch(LogStateActions.setNodeLogs({ ExecID, logs }))
//       } catch (error: any) {
//         console.error('Error fetching node logs:', error)
//         setError(error)
//       }
//     }

//     fetchAndStoreNodeLogs()
//   }, [dispatch, ExecID])

//   return { nodeLogs, isLoading, error }
// }
