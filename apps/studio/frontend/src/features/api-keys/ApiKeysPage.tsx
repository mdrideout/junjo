import { useEffect } from 'react'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { RootState } from '../../root-store/store'
import TrashIcon from '@heroicons/react/24/outline/TrashIcon'
import { CredentialCopyButton } from '../../components/credentials/credential-copy-button'
import CreateApiKeyDialog from './CreateApiKeyDialog'
import OtelExporterGuide from './components/OtelExporterGuide'
import { ApiKeysStateActions } from './slice'

export default function ApiKeysPage() {
  const dispatch = useAppDispatch()
  const { apiKeys, loading, error } = useAppSelector((state: RootState) => state.apiKeysState)

  // Fetch data when the component mounts
  useEffect(() => {
    dispatch(ApiKeysStateActions.fetchApiKeysData({ force: false }))
  }, [dispatch])

  // Render the list
  return (
    <div className={'flex h-dvh flex-col overflow-y-auto px-5 py-6'}>
      <div>
        <h1>Application Telemetry API Keys</h1>
        <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
          Authenticate telemetry sent from your application to Junjo AI Studio.
        </p>
      </div>
      <hr className={'my-4'} />
      <div>
        <CreateApiKeyDialog />
      </div>
      {error !== null && (
        <p role="alert" className="mt-4 text-sm text-red-700 dark:text-red-300">
          {error}
        </p>
      )}
      <div className="mt-4 shrink-0 overflow-x-auto">
        {loading && apiKeys.length === 0 ? (
          <p className="text-sm text-[var(--studio-text-muted)]">Loading API keys…</p>
        ) : error === null && apiKeys.length === 0 ? (
          <div className={'text-sm text-zinc-500 dark:text-zinc-400'}>
            No application telemetry API keys have been created.
          </div>
        ) : apiKeys.length > 0 ? (
          <table className="w-full max-w-[1024px] text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--studio-border)]">
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Created</th>
                <th className="px-3 py-2">Key</th>
                <th className="px-3 py-2">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {apiKeys.map((apiKey) => {
                // Make date human readable
                const createdAt = new Date(apiKey.created_at)
                const createdAtString = createdAt.toLocaleString()
                const truncatedKey = apiKey.key.length > 12 ? apiKey.key.slice(0, 12) + '...' : apiKey.key

                return (
                  <tr key={apiKey.id} className="border-b border-[var(--studio-border)] last:border-0">
                    <td className="px-3 py-3 font-medium">{apiKey.name}</td>
                    <td className="px-3 py-3">{createdAtString}</td>
                    <td className="px-3 py-3 font-mono">{truncatedKey}</td>
                    <td className="px-3 py-3 text-right">
                      <div className="flex justify-end gap-2">
                        <CredentialCopyButton label={`API key ${apiKey.name}`} value={apiKey.key} />
                        <button
                          type="button"
                          aria-label={`Delete API key ${apiKey.name}`}
                          className="rounded-md p-1 hover:bg-[var(--studio-surface-hover)]"
                          onClick={() => {
                            if (confirm(`Are you sure you want to delete key ${apiKey.name}?`)) {
                              dispatch(ApiKeysStateActions.deleteApiKey({ id: apiKey.id }))
                            }
                          }}
                        >
                          <TrashIcon className={'size-4'} />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : null}
      </div>

      {/* Getting Started Guide - Below the table */}
      <div className={'mt-12'}>
        <OtelExporterGuide />
      </div>
    </div>
  )
}
