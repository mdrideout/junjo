import { useEffect, useState } from 'react'
import { fetchAppNames } from '../fetch/fetch-app-names'
import { LogStateActions, selectAppNames } from '../store/slice'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'

export const useFetchAppNames = () => {
  const dispatch = useAppDispatch()
  const appNames = useAppSelector(selectAppNames)
  const isLoading = appNames.length === 0 //  Simple
  const [error, setError] = useState<boolean>(false)

  useEffect(() => {
    const fetchAndStoreAppNames = async () => {
      setError(false)

      try {
        const names = await fetchAppNames()
        dispatch(LogStateActions.setAppNames(names))
      } catch (error) {
        console.error('Error fetching app names:', error)
        setError(true)
      }
    }

    fetchAndStoreAppNames()
  }, [dispatch])

  return { appNames, isLoading, error }
}
