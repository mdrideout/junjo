// import { useEffect, useState } from 'react'
// import { fetchWorkflowMetadata } from '../fetch/fetch-workflow-metadata'
// import { LogStateActions, selectWorkflowExecution } from '../store/slice'
// import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
// import { RootState } from '../../../root-store/store'

// export const useFetchWorkflowExecution = (ExecID: string | undefined) => {
//   const dispatch = useAppDispatch()
//   const workflowExecution = useAppSelector((state: RootState) => selectWorkflowExecution(state, ExecID ?? ''))
//   const isLoading = workflowExecution === undefined
//   const [error, setError] = useState<boolean>(false)

//   useEffect(() => {
//     if (!ExecID) return

//     const fetchAndStoreWorkflowExecution = async () => {
//       setError(false)
//       try {
//         const execution = await fetchWorkflowMetadata(ExecID)
//         dispatch(LogStateActions.upsertWorkflowExecution(execution))
//       } catch (error) {
//         console.error('Error fetching workflow executions:', error)
//         setError(true)
//       }
//     }

//     fetchAndStoreWorkflowExecution()
//   }, [dispatch, ExecID])

//   return { workflowExecution, isLoading, error }
// }
