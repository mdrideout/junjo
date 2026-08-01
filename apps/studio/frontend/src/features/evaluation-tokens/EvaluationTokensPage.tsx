import { useEffect } from 'react'
import { AppLink } from '../../components/navigation/app-link'
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
      <nav aria-label="Breadcrumb" className="mb-4 text-sm">
        <AppLink to="/settings/credentials">Developer credentials</AppLink>
      </nav>
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-xl font-semibold">Evaluation tokens</h1>
          <p className="mt-1 max-w-3xl text-sm text-[var(--studio-text-muted)]">
            Scoped credentials for the Junjo evaluation CLI and SDK. These tokens are
            separate from ingestion API keys and cannot deliver telemetry.
          </p>
        </div>
        <div className="ml-auto">
          <CreateEvaluationTokenDialog />
        </div>
      </div>

      {error !== null && (
        <p role="alert" className="mt-5 text-sm text-red-700 dark:text-red-300">
          {error}
        </p>
      )}

      <div className="mt-6 overflow-x-auto">
        {loading && items.length === 0 ? (
          <p className="text-sm text-[var(--studio-text-muted)]">Loading tokens…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-[var(--studio-text-muted)]">
            No evaluation tokens have been created.
          </p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--studio-border)]">
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Prefix</th>
                <th className="px-3 py-2">Scopes</th>
                <th className="px-3 py-2">Expires</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((token) => {
                const revoked = token.revoked_at !== null
                const expired =
                  token.expires_at !== null && new Date(token.expires_at) <= new Date()
                const active = !revoked && !expired
                return (
                  <tr
                    key={token.id}
                    className="border-b border-[var(--studio-border)] last:border-0"
                  >
                    <td className="px-3 py-3 font-medium">{token.name}</td>
                    <td className="px-3 py-3 font-mono">{token.prefix}</td>
                    <td className="px-3 py-3">{token.scopes.join(', ')}</td>
                    <td className="px-3 py-3">{formatDate(token.expires_at)}</td>
                    <td className="px-3 py-3">
                      {revoked ? 'Revoked' : expired ? 'Expired' : 'Active'}
                    </td>
                    <td className="px-3 py-3 text-right">
                      <button
                        type="button"
                        disabled={!active || loading}
                        className="rounded-md border border-[var(--studio-border-strong)] px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50"
                        onClick={() => {
                          if (
                            confirm(
                              `Revoke evaluation token "${token.name}"? This cannot be undone.`,
                            )
                          ) {
                            dispatch(EvaluationTokensActions.revokeToken({ id: token.id }))
                          }
                        }}
                      >
                        Revoke
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
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
