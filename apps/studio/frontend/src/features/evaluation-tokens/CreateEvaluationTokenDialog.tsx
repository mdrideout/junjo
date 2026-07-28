import { PlusIcon } from '@heroicons/react/24/outline'
import { useEffect, useState, type FormEvent } from 'react'
import { ActionButton } from '../../components/actions/action-button'
import { Modal, ModalFooter } from '../../components/overlays/modal'
import { useAppDispatch } from '../../root-store/hooks'
import { createEvaluationToken } from './fetch/create-evaluation-token'
import type {
  EvaluationTokenCreated,
  EvaluationTokenScope,
} from './schemas'
import { EvaluationTokensActions } from './store/slice'

const AVAILABLE_SCOPES: ReadonlyArray<{
  value: EvaluationTokenScope
  label: string
  description: string
}> = [
  {
    value: 'evaluation:read',
    label: 'Evaluation read',
    description: 'List datasets, runs, attempts, and execution membership.',
  },
  {
    value: 'evaluation:write',
    label: 'Evaluation write',
    description: 'Create datasets and cases, start runs, and record results.',
  },
  {
    value: 'evidence:read',
    label: 'Evidence read',
    description: 'Resolve executions and retrieve their received trace evidence.',
  },
]

export default function CreateEvaluationTokenDialog() {
  const dispatch = useAppDispatch()
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<EvaluationTokenCreated | null>(null)

  useEffect(() => {
    if (!open) {
      setLoading(false)
      setError(null)
      setCreated(null)
    }
  }, [open])

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setLoading(true)
    setError(null)

    const form = new FormData(event.currentTarget)
    const scopes = AVAILABLE_SCOPES.flatMap(({ value }) =>
      form.get(value) === 'on' ? [value] : [],
    )

    try {
      const rawExpiration = String(form.get('expires_at') ?? '').trim()
      const expiresAt =
        rawExpiration === '' ? null : new Date(rawExpiration).toISOString()
      const token = await createEvaluationToken({
        name: String(form.get('name') ?? ''),
        scopes,
        expires_at: expiresAt,
      })
      setCreated(token)
      dispatch(EvaluationTokensActions.fetchTokens({ force: true }))
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : 'Failed to create evaluation token.',
      )
    } finally {
      setLoading(false)
    }
  }

  const copyToken = async () => {
    if (created === null) return
    try {
      await navigator.clipboard.writeText(created.token)
    } catch {
      setError('The token could not be copied. Copy it manually before closing.')
    }
  }

  return (
    <>
      <ActionButton size="compact" intent="secondary" onClick={() => setOpen(true)}>
        <PlusIcon className="size-4" /> Create token
      </ActionButton>
      <Modal
        open={open}
        onOpenChange={setOpen}
        title="Create evaluation token"
        description="Create a separately scoped credential for Junjo evaluation automation. It cannot send OTLP telemetry."
      >
        {created === null ? (
          <form onSubmit={submit}>
            <div className="flex flex-col gap-5">
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                Token name
                <input
                  name="name"
                  required
                  maxLength={128}
                  placeholder="Local coding agent"
                  className="rounded-lg border border-[var(--studio-border-strong)] bg-[var(--studio-surface-raised)] px-3 py-2 font-normal outline-none focus:border-[var(--studio-focus-ring)]"
                />
              </label>
              <fieldset className="flex flex-col gap-3">
                <legend className="text-sm font-medium">Scopes</legend>
                {AVAILABLE_SCOPES.map((scope) => (
                  <label
                    key={scope.value}
                    className="flex items-start gap-3 rounded-lg border border-[var(--studio-border)] p-3"
                  >
                    <input
                      type="checkbox"
                      name={scope.value}
                      defaultChecked
                      className="mt-1"
                    />
                    <span>
                      <span className="block text-sm font-medium">{scope.label}</span>
                      <span className="block text-xs text-[var(--studio-text-muted)]">
                        {scope.description}
                      </span>
                    </span>
                  </label>
                ))}
              </fieldset>
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                Expires at (optional)
                <input
                  type="datetime-local"
                  name="expires_at"
                  className="rounded-lg border border-[var(--studio-border-strong)] bg-[var(--studio-surface-raised)] px-3 py-2 font-normal outline-none focus:border-[var(--studio-focus-ring)]"
                />
              </label>
              {error !== null && (
                <p role="alert" className="text-sm text-red-700 dark:text-red-300">
                  {error}
                </p>
              )}
            </div>
            <ModalFooter>
              <ActionButton intent="secondary" onClick={() => setOpen(false)}>
                Cancel
              </ActionButton>
              <ActionButton disabled={loading} type="submit">
                Create token
              </ActionButton>
            </ModalFooter>
          </form>
        ) : (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-[var(--studio-text-muted)]">
              Copy this token now. Studio stores only its hash and cannot show it again.
            </p>
            <code className="break-all rounded-lg border border-[var(--studio-border)] bg-[var(--studio-surface-raised)] p-3 text-sm">
              {created.token}
            </code>
            {error !== null && (
              <p role="alert" className="text-sm text-red-700 dark:text-red-300">
                {error}
              </p>
            )}
            <ModalFooter>
              <ActionButton intent="secondary" onClick={copyToken}>
                Copy token
              </ActionButton>
              <ActionButton onClick={() => setOpen(false)}>Done</ActionButton>
            </ModalFooter>
          </div>
        )}
      </Modal>
    </>
  )
}
