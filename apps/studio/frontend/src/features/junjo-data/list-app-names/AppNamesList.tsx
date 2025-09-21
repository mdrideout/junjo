import { useNavigate } from 'react-router'
import { useAppDispatch, useAppSelector } from '../../../root-store/hooks'
import {
  selectServiceNames,
  selectServiceNamesError,
  selectServiceNamesLoading,
} from '../../otel/store/selectors'
import { useEffect } from 'react'
import { OtelStateActions } from '../../otel/store/slice'

export default function AppNamesList() {
  const navigate = useNavigate()
  const dispatch = useAppDispatch()

  const loading = useAppSelector(selectServiceNamesLoading)
  const error = useAppSelector(selectServiceNamesError)
  const serviceNames = useAppSelector(selectServiceNames)

  // Fetch the serviceNames
  useEffect(() => {
    dispatch(OtelStateActions.fetchServiceNames())
  }, [])

  if (loading) {
    return null
  }

  if (error) {
    return <div>Error fetching app names.</div> //Improved error display
  }

  return (
    <table className="text-left text-sm">
      <thead>
        <tr>
          <th className={'px-4 py-1'}>Apps</th>
        </tr>
      </thead>
      <tbody>
        {serviceNames.map((item) => (
          <tr key={item} className={'last-of-type:border-0 border-b border-zinc-200 dark:border-zinc-600'}>
            <td className={'px-4 py-1.5'}>{item}</td>
            <td
              className={'px-4 py-1.5 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer underline'}
              onClick={() => navigate(`${item}`)}
            >
              Workflow Executions
            </td>
            <td
              className={'px-4 py-1.5 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer underline'}
              onClick={() => navigate(`/traces/${item}`)}
            >
              Traces
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
