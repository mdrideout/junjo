import { useEffect } from 'react'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { RootState } from '../../root-store/store'
import TrashIcon from '@heroicons/react/24/outline/TrashIcon'
import ApiKeyCopyButton from './ApiKeyCopyButton'
import CreateApiKeyDialog from './CreateApiKeyDialog'
import { ApiKeysStateActions } from './slice'

export default function ApiKeysPage() {
  const dispatch = useAppDispatch()
  const { apiKeys, loading, error } = useAppSelector((state: RootState) => state.apiKeysState)

  // Fetch data when the component mounts
  useEffect(() => {
    dispatch(ApiKeysStateActions.fetchApiKeysData({ force: false }))
  }, [dispatch])

  // Handle loading and error states
  if (loading) {
    return <div className={'h-full w-full flex items-center justify-center'}>Loading...</div>
  }
  if (error) {
    return <div className={'h-full w-full flex items-center justify-center'}>Error: {error}</div>
  }

  // Render the list
  return (
    <div className={'px-3 py-4 flex flex-col h-dvh overflow-hidden'}>
      <div className={'flex gap-x-3 px-2 items-center'}>
        <div className={'flex gap-x-3 font-bold'}>API Keys</div>
        <CreateApiKeyDialog />
      </div>
      <hr className={'my-4'} />
      <div className={'px-2'}>
        {apiKeys.length === 0 && (
          <div className={'text-sm text-zinc-500 dark:text-zinc-400'}>
            No API keys found. Create one to get started.
          </div>
        )}
        {apiKeys.length > 0 && (
          <table className="text-left text-sm">
            <thead>
              <tr>
                <th className={'px-4 py-1'}>Name</th>
                <th className={'px-4 py-1'}>Created At</th>
                <th className={'px-4 py-1'}>Key</th>
                <th className={'px-4 py-1'}></th>
                <th className={'px-4 py-1'}></th>
              </tr>
            </thead>
            <tbody>
              {apiKeys.map((apiKey) => {
                // Make date human readable
                const createdAt = new Date(apiKey.CreatedAt)
                const createdAtString = createdAt.toLocaleString()
                const truncatedKey = apiKey.Key.length > 12 ? apiKey.Key.slice(0, 12) + '...' : apiKey.Key

                return (
                  <tr
                    key={apiKey.Key}
                    className={'last-of-type:border-0 border-b border-zinc-200 dark:border-zinc-600'}
                  >
                    <td className={'px-4 py-1.5'}>{apiKey.Name}</td>
                    <td className={'px-4 py-1.5 font-mono'}>{createdAtString}</td>
                    <td className={'px-4 py-1.5 font-mono'}>{truncatedKey}</td>

                    {/* Copy button */}
                    <td className={' text-center'}>
                      <ApiKeyCopyButton apiKey={apiKey.Key} />
                    </td>

                    {/* Delete button */}
                    <td className={' text-center'}>
                      <button
                        className={'p-1 hover:bg-zinc-300 dark:hover:bg-zinc-700 rounded-md cursor-pointer'}
                        onClick={() => {
                          if (confirm(`Are you sure you want to delete key ${apiKey.Name}?`)) {
                            dispatch(ApiKeysStateActions.deleteApiKey({ key: apiKey.Key }))
                          }
                        }}
                      >
                        <TrashIcon className={'size-4'} />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
