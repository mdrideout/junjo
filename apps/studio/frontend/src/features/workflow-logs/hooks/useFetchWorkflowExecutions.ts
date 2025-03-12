import { useEffect, useState } from 'react'
import { fetchWorkflowMetadataList } from '../fetch/fetch-workflow-metadata'
import { LogStateActions, selectWorkflowExecutions } from '../store/slice'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'

export const useFetchWorkflowExecutions = (appName: string | undefined) => {
  const dispatch = useAppDispatch()
  const workflowExecutions = useAppSelector(selectWorkflowExecutions)
  const isLoading = workflowExecutions.length === 0
  const [error, setError] = useState<boolean>(false)

  useEffect(() => {
    if (!appName) return

    const fetchAndStoreWorkflowExecutions = async () => {
      setError(false)
      try {
        const executions = await fetchWorkflowMetadataList(appName)
        dispatch(LogStateActions.setWorkflowExecutions(executions))
      } catch (error) {
        console.error('Error fetching workflow executions:', error)
        setError(true)
      }
    }

    fetchAndStoreWorkflowExecutions()
  }, [dispatch, appName])

  return { workflowExecutions, isLoading, error }
}
