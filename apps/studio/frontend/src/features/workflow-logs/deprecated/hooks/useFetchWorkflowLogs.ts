// // LEFT OFF: See gemini chat for new hook / slice / and component implementation
// import { useEffect, useState } from 'react'
// import { fetchWorkflowLogs } from '../fetch/fetch-workflow-logs'
// import { LogStateActions, selectWorkflowLogs } from '../store/slice'
// import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'

// export const useFetchWorkflowLogs = (execId: string) => {
//   const dispatch = useAppDispatch()
//   const workflowLogs = useAppSelector((state) => selectWorkflowLogs(state, execId))
//   const isLoading = workflowLogs === undefined && execId !== ''
//   const [error, setError] = useState<Error | null>(null)

//   useEffect(() => {
//     const fetchAndStoreWorkflowLogs = async () => {
//       setError(null)
//       if (execId === '') return

//       try {
//         const logs = await fetchWorkflowLogs(execId)
//         dispatch(LogStateActions.setWorkflowLogs({ execId, logs }))
//       } catch (error: any) {
//         console.error('Error fetching workflow logs:', error)
//         setError(error)
//       }
//     }

//     fetchAndStoreWorkflowLogs()
//   }, [dispatch, execId])

//   return { workflowLogs, isLoading, error }
// }
