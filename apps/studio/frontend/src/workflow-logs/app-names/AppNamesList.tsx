import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { fetchAppNames } from '../fetch/fetch-app-names'

export default function AppNamesList() {
  const navigate = useNavigate()

  const {
    data: namesList,
    isLoading,
    isError,
    error,
  } = useQuery<string[], Error>({
    queryKey: ['appNamesList'],
    queryFn: fetchAppNames,
    select: (data) => data,
    // refetchInterval: 1000 * 3,
  })

  if (isLoading) {
    return null
  }

  if (isError) {
    return <div>Error: {error.message}</div>
  }

  if (!namesList) {
    return null
  }

  return (
    <table className="text-left w-full">
      <thead>
        <tr>
          <th className={'px-4 py-1'}>Apps</th>
        </tr>
      </thead>
      <tbody>
        {namesList.map((item) => {
          return (
            <tr
              key={item}
              className={
                'last-of-type:border-0 border-b border-zinc-200 dark:border-zinc-600 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer'
              }
              onClick={() => navigate(`${item}`)}
            >
              <td className={'px-4 py-1.5'}>{item}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
