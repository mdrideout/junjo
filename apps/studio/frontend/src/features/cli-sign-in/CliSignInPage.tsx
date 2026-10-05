import { useEffect, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router'
import { requestFailureMessage } from '../../auth/api-error'
import { ActionButton } from '../../components/actions/action-button'
import { AppLink } from '../../components/navigation/app-link'
import { AVAILABLE_SCOPES } from '../evaluation-tokens/available-scopes'
import { approveCliSignIn } from './fetch/approve-cli-sign-in'
import { denyCliSignIn } from './fetch/deny-cli-sign-in'
import { getCliSignIn } from './fetch/get-cli-sign-in'
import type { CliSignInApproved, CliSignInRead } from './schemas'

/**
 * The approval page of the CLI browser sign-in (Studio ADR-012). The terminal
 * links here with its user code in the `code` query parameter. The URL is the
 * one owner of which code the page is about.
 */
export default function CliSignInPage() {
  const [searchParameters, setSearchParameters] = useSearchParams()
  // Studio compares the code without its hyphen and without regard to case,
  // so the page passes on what it was given, without surrounding whitespace.
  const userCode = (searchParameters.get('code') ?? '').trim()

  return (
    <div className="flex h-dvh flex-col overflow-y-auto px-5 py-6">
      <div>
        <h1>CLI sign-in</h1>
        <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
          Approve or deny a sign-in that the Junjo CLI started in a terminal.
        </p>
      </div>
      <hr className="my-4" />
      <div className="max-w-xl">
        {userCode === '' ? (
          <UserCodeForm onSubmit={(code) => setSearchParameters({ code })} />
        ) : (
          <CliSignInRequest key={userCode} userCode={userCode} />
        )}
      </div>
    </div>
  )
}

function UserCodeForm({ onSubmit }: { onSubmit: (userCode: string) => void }) {
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onSubmit(String(new FormData(event.currentTarget).get('code') ?? ''))
  }

  return (
    <form onSubmit={submit} className="flex flex-col items-start gap-4">
      <label className="flex flex-col gap-1.5 text-sm font-medium">
        Code shown in your terminal
        <input
          name="code"
          required
          autoComplete="off"
          spellCheck={false}
          className="rounded-lg border border-[var(--studio-border-strong)] bg-[var(--studio-surface-raised)] px-3 py-2 font-mono font-normal outline-none focus:border-[var(--studio-focus-ring)]"
        />
      </label>
      <ActionButton type="submit">Continue</ActionButton>
    </form>
  )
}

type RequestState =
  | { phase: 'loading' }
  | { phase: 'pending'; signIn: CliSignInRead }
  | { phase: 'approved'; approved: CliSignInApproved }
  | { phase: 'denied' }
  | { phase: 'not-found' }
  | { phase: 'failed'; message: string }

function CliSignInRequest({ userCode }: { userCode: string }) {
  const [state, setState] = useState<RequestState>({ phase: 'loading' })
  const [deciding, setDeciding] = useState(false)
  const [decisionError, setDecisionError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    void getCliSignIn(userCode, controller.signal)
      .then((signIn) => {
        if (controller.signal.aborted) return
        setState(signIn === null ? { phase: 'not-found' } : { phase: 'pending', signIn })
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return
        setState({ phase: 'failed', message: requestFailureMessage(reason) })
      })

    return () => controller.abort()
  }, [userCode])

  // The decision is sent for the code the page shows, as Studio formatted it.
  const decide = async (decision: 'approve' | 'deny', signIn: CliSignInRead) => {
    setDeciding(true)
    setDecisionError(null)
    try {
      if (decision === 'approve') {
        const approved = await approveCliSignIn(signIn.user_code)
        setState(approved === null ? { phase: 'not-found' } : { phase: 'approved', approved })
      } else {
        const denied = await denyCliSignIn(signIn.user_code)
        setState(denied === null ? { phase: 'not-found' } : { phase: 'denied' })
      }
    } catch (caught) {
      setDecisionError(requestFailureMessage(caught))
    } finally {
      setDeciding(false)
    }
  }

  if (state.phase === 'loading') {
    return <p className="text-sm text-[var(--studio-text-muted)]">Loading sign-in request…</p>
  }

  if (state.phase === 'failed') {
    return (
      <p role="alert" className="text-sm text-red-700 dark:text-red-300">
        {state.message}
      </p>
    )
  }

  if (state.phase === 'not-found') {
    return (
      <section
        role="alert"
        className="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-surface)] p-4"
      >
        <h2>This code cannot be used</h2>
        <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
          It is unknown, already used, or expired. Run the command again in your terminal to get a
          new code.
        </p>
      </section>
    )
  }

  if (state.phase === 'approved') {
    return (
      <section
        role="status"
        className="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-surface)] p-4"
      >
        <h2>Sign-in approved</h2>
        <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
          The terminal will finish signing in by itself with a new developer access token named:
        </p>
        <p className="mt-2 break-words rounded-lg border border-[var(--studio-border)] bg-[var(--studio-surface-raised)] p-3 text-sm">
          {state.approved.token_name}
        </p>
        <p className="mt-3 text-sm text-[var(--studio-text-muted)]">
          You can revoke this token on the{' '}
          <AppLink to="/access-tokens">Developer Access Tokens</AppLink> page.
        </p>
      </section>
    )
  }

  if (state.phase === 'denied') {
    return (
      <section
        role="status"
        className="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-surface)] p-4"
      >
        <h2>Sign-in denied</h2>
        <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
          The terminal was not given access to Junjo AI Studio.
        </p>
      </section>
    )
  }

  const { signIn } = state
  const requestedScopes = AVAILABLE_SCOPES.filter((scope) => signIn.scopes.includes(scope.value))

  return (
    <div className="flex flex-col gap-6">
      <section
        aria-labelledby="cli-sign-in-code-heading"
        className="rounded-lg border border-[var(--studio-border-strong)] bg-[var(--studio-surface-raised)] p-5"
      >
        <h2 id="cli-sign-in-code-heading">Compare this code with your terminal</h2>
        <p className="mt-3 font-mono text-4xl font-bold tracking-widest">{signIn.user_code}</p>
        <p className="mt-3 text-sm text-[var(--studio-text-muted)]">
          Your own terminal must be showing this exact code.
        </p>
      </section>

      <dl className="flex flex-col gap-4">
        <div>
          <dt className="text-sm font-medium">Reported by the terminal as</dt>
          <dd className="mt-1.5 break-words rounded-lg border border-[var(--studio-border)] bg-[var(--studio-surface)] p-3 text-sm">
            {signIn.client_name}
          </dd>
          <dd className="mt-1 text-xs text-[var(--studio-text-muted)]">
            The terminal chose this name. Junjo AI Studio has not verified it.
          </dd>
        </div>
        <div>
          <dt className="text-sm font-medium">Requested scopes</dt>
          <dd className="mt-1.5 text-sm">
            <ul>
              {requestedScopes.map((scope) => (
                <li key={scope.value}>
                  <span className="block font-medium">{scope.label}</span>
                  <span className="block text-xs text-[var(--studio-text-muted)]">
                    {scope.description}
                  </span>
                </li>
              ))}
            </ul>
          </dd>
        </div>
        <div>
          <dt className="text-sm font-medium">Request expires</dt>
          <dd className="mt-1.5 text-sm">{new Date(signIn.expires_at).toLocaleString()}</dd>
        </div>
      </dl>

      <div className="text-sm">
        <p className="font-medium">
          Approving gives that terminal access to Junjo AI Studio as you, with the scopes listed
          above.
        </p>
        <p className="mt-1">
          If you did not just see this code in your own terminal, deny this request.
        </p>
      </div>

      {decisionError !== null && (
        <p role="alert" className="text-sm text-red-700 dark:text-red-300">
          {decisionError}
        </p>
      )}

      <div className="flex flex-wrap gap-3">
        <ActionButton disabled={deciding} onClick={() => void decide('approve', signIn)}>
          Approve
        </ActionButton>
        <ActionButton
          intent="secondary"
          disabled={deciding}
          onClick={() => void decide('deny', signIn)}
        >
          Deny
        </ActionButton>
      </div>
    </div>
  )
}
