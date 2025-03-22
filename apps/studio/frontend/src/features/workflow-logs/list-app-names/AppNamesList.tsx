import { useNavigate } from 'react-router'
import { useFetchAppNames } from '../../hooks/useFetchAppNames'

export default function AppNamesList() {
  const navigate = useNavigate()
  const { appNames, isLoading, error } = useFetchAppNames()

  if (isLoading) {
    return null
  }

  if (error) {
    return <div>Error fetching app names.</div> //Improved error display
  }

  return (
    <table className="text-left text-sm w-full">
      <thead>
        <tr>
          <th className={'px-4 py-1'}>Apps</th>
        </tr>
      </thead>
      <tbody>
        {appNames.map((item) => (
          <tr
            key={item}
            className={
              'last-of-type:border-0 border-b border-zinc-200 dark:border-zinc-600 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer'
            }
            onClick={() => navigate(`${item}`)}
          >
            <td className={'px-4 py-1.5'}>{item}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
