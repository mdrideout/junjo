import TrashIcon from '@heroicons/react/24/outline/TrashIcon'
import { useEffect } from 'react'
import { CredentialCopyButton } from '../../components/credentials/credential-copy-button'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import CreateEvaluationTokenDialog from './CreateEvaluationTokenDialog'
import { EvaluationTokensActions } from './store/slice'

function formatDate(value: string | null): string {
  return value === null ? 'Never' : new Date(value).toLocaleString()
}

export default function EvaluationTokensPage() {
  const dispatch = useAppDispatch()
  const { items, loading, error, nextCursor } = useAppSelector(
    (state) => state.evaluationTokensState,
  )

  useEffect(() => {
    dispatch(EvaluationTokensActions.fetchTokens({ force: false }))
  }, [dispatch])

  return (
    <div className="flex h-dvh flex-col overflow-y-auto px-5 py-6">
      <div>
        <h1>Developer Access Tokens</h1>
        <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
          Authenticate developer environments and coding agents that interact with
          Junjo AI Studio through the Junjo SDK and CLI.
        </p>
      </div>
      <hr className="my-4" />
      <div>
        <CreateEvaluationTokenDialog />
      </div>

      {error !== null && (
        <p role="alert" className="mt-4 text-sm text-red-700 dark:text-red-300">
          {error}
        </p>
      )}

      <div className="mt-4 shrink-0 overflow-x-auto">
        {loading && items.length === 0 ? (
          <p className="text-sm text-[var(--studio-text-muted)]">Loading tokens…</p>
        ) : error === null && items.length === 0 ? (
          <p className="text-sm text-[var(--studio-text-muted)]">
            No developer access tokens have been created.
          </p>
        ) : items.length > 0 ? (
          <table className="w-full max-w-[1024px] text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--studio-border)]">
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Scopes</th>
                <th className="px-3 py-2">Expires</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Token</th>
                <th className="px-3 py-2">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((token) => {
                const expired =
                  token.expires_at !== null && new Date(token.expires_at) <= new Date()
                const abbreviatedToken =
                  token.token.length > 12
                    ? `${token.token.slice(0, 12)}...`
                    : token.token
                return (
                  <tr
                    key={token.id}
                    className="border-b border-[var(--studio-border)] last:border-0"
                  >
                    <td className="px-3 py-3 font-medium">{token.name}</td>
                    <td className="px-3 py-3">{token.scopes.join(', ')}</td>
                    <td className="px-3 py-3">{formatDate(token.expires_at)}</td>
                    <td className="px-3 py-3">
                      {expired ? 'Expired' : 'Active'}
                    </td>
                    <td className="px-3 py-3 font-mono">{abbreviatedToken}</td>
                    <td className="px-3 py-3 text-right">
                      <div className="flex justify-end gap-2">
                        <CredentialCopyButton
                          label={`access token ${token.name}`}
                          value={token.token}
                        />
                        <button
                          type="button"
                          disabled={loading}
                          aria-label={`Delete access token ${token.name}`}
                          className="rounded-md p-1 hover:bg-[var(--studio-surface-hover)] disabled:cursor-not-allowed disabled:opacity-50"
                          onClick={() => {
                            if (confirm(`Delete access token "${token.name}"?`)) {
                              dispatch(EvaluationTokensActions.deleteToken({ id: token.id }))
                            }
                          }}
                        >
                          <TrashIcon className="size-4" />
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
      {nextCursor !== null && (
        <div className="mt-4">
          <button
            type="button"
            disabled={loading}
            className="rounded-md border border-[var(--studio-border-strong)] px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
            onClick={() => {
              dispatch(
                EvaluationTokensActions.fetchTokens({
                  force: true,
                  cursor: nextCursor,
                }),
              )
            }}
          >
            {loading ? 'Loading…' : 'Load more'}
          </button>
        </div>
      )}
    </div>
  )
}
