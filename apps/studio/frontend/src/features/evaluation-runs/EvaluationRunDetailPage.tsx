import { useEffect } from 'react'
import { useParams } from 'react-router'
import ErrorPage from '../../components/errors/ErrorPage'
import { AppLink } from '../../components/navigation/app-link'
import { useAppDispatch, useAppSelector } from '../../root-store/hooks'
import { EvaluationStatusBadge } from './components/EvaluationStatusBadge'
import { SemanticExecutionLink } from './components/SemanticExecutionLink'
import { EvaluationIdSchema } from './schemas/evaluation-runs'
import { selectEvaluationRunDetailRequest } from './store/selectors'
import { EvaluationRunsActions } from './store/slice'

function displayScore(score: number | null): string {
  return score === null ? '—' : score.toFixed(2)
}

function displayDuration(durationMs: number | null): string {
  return durationMs === null ? '—' : `${durationMs} ms`
}

export default function EvaluationRunDetailPage() {
  const { runId } = useParams()
  const parsedRunId = EvaluationIdSchema.safeParse(runId)
  const validatedRunId = parsedRunId.success ? parsedRunId.data : ''
  const dispatch = useAppDispatch()
  const request = useAppSelector((state) =>
    selectEvaluationRunDetailRequest(state, validatedRunId),
  )

  useEffect(() => {
    if (validatedRunId) dispatch(EvaluationRunsActions.fetchEvaluationRun(validatedRunId))
  }, [dispatch, validatedRunId])

  if (!parsedRunId.success) {
    return <ErrorPage title="Invalid evaluation run" message="A non-empty evaluation run ID is required." />
  }

  if (request.loading && request.data === null) {
    return <div className="p-6 text-sm text-[var(--studio-text-muted)]">Loading evaluation run…</div>
  }
  if (request.error !== null) {
    return <ErrorPage title="Evaluation run unavailable" message={request.error} />
  }
  if (request.data === null) {
    return <div className="p-6 text-sm text-[var(--studio-text-muted)]">No evaluation run found.</div>
  }

  const { run, dataset, cases } = request.data
  return (
    <div className="mx-auto max-w-[110rem] space-y-5 p-4 sm:p-6">
      <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-2 text-sm text-[var(--studio-text-muted)]">
        <AppLink to="/evaluation-runs">Evaluation runs</AppLink>
        <span aria-hidden="true">/</span>
        <span>{run.candidate_label}</span>
      </nav>

      <header className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)] p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-sm font-semibold text-[var(--studio-text-muted)]">{dataset.name}</div>
            <h1 className="m-0 mt-1 text-3xl">{run.candidate_label}</h1>
            <div className="mt-2 font-mono text-xs text-[var(--studio-text-subtle)]">{run.id}</div>
          </div>
          <EvaluationStatusBadge status={run.status} />
        </div>
        <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Dataset</dt>
            <dd className="mt-1 text-sm font-semibold">{dataset.key}</dd>
            <dd className="mt-1 font-mono text-xs">{dataset.id}</dd>
          </div>
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Source revision</dt>
            <dd className="mt-1 break-all font-mono text-xs">{run.source_revision}</dd>
          </div>
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Created</dt>
            <dd className="mt-1 text-sm">{new Date(run.created_at).toLocaleString()}</dd>
          </div>
          <div className="rounded-lg bg-[var(--studio-page)] p-3">
            <dt className="text-xs text-[var(--studio-text-subtle)]">Completed</dt>
            <dd className="mt-1 text-sm">
              {run.completed_at === null ? 'Still active' : new Date(run.completed_at).toLocaleString()}
            </dd>
          </div>
        </dl>
        {dataset.description !== null && (
          <p className="mt-4 text-sm text-[var(--studio-text-muted)]">{dataset.description}</p>
        )}
      </header>

      <section>
        <div className="mb-3">
          <h2 className="m-0 text-xl">Case outcomes</h2>
          <p className="mt-1 text-sm text-[var(--studio-text-muted)]">
            Outcomes are Studio evaluation records. Evidence opens through the exact semantic execution resolver.
          </p>
        </div>
        <div className="overflow-x-auto rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)]">
          <table className="w-full min-w-[78rem] text-left text-sm">
            <thead className="bg-[var(--studio-surface)] text-xs uppercase tracking-wide text-[var(--studio-text-subtle)]">
              <tr>
                <th scope="col" className="px-3 py-3">Case</th>
                <th scope="col" className="px-3 py-3">Target</th>
                <th scope="col" className="px-3 py-3">Status</th>
                <th scope="col" className="px-3 py-3">Score</th>
                <th scope="col" className="px-3 py-3">Reason</th>
                <th scope="col" className="px-3 py-3">Duration</th>
                <th scope="col" className="px-3 py-3">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((item) => (
                <tr key={item.case.id} className="border-b border-[var(--studio-border)] last:border-0">
                  <th scope="row" className="px-3 py-3 text-left">
                    <span className="font-semibold">{item.case.case_key}</span>
                    <span className="mt-1 block text-xs font-normal text-[var(--studio-text-subtle)]">
                      #{item.case.ordinal} · {item.case.origin}
                    </span>
                  </th>
                  <td className="px-3 py-3">
                    <span className="font-mono text-xs">{item.case.target_key}</span>
                    <span className="mt-1 block text-xs text-[var(--studio-text-subtle)]">
                      {item.case.target_kind} · input v{item.case.input_version} · evaluator v{item.case.evaluator_version}
                    </span>
                  </td>
                  <td className="px-3 py-3"><EvaluationStatusBadge status={item.attempt.status} /></td>
                  <td className="px-3 py-3 font-mono text-xs">{displayScore(item.attempt.score)}</td>
                  <td className="max-w-xl whitespace-pre-wrap px-3 py-3 text-xs">
                    {item.attempt.reason ?? '—'}
                  </td>
                  <td className="px-3 py-3 font-mono text-xs">
                    {displayDuration(item.attempt.duration_ms)}
                  </td>
                  <td className="px-3 py-3 text-xs">
                    <div className="flex flex-col items-start gap-2">
                      {item.attempt.subject_execution === null ? (
                        <span className="text-[var(--studio-text-subtle)]">No subject execution</span>
                      ) : (
                        <SemanticExecutionLink
                          execution={item.attempt.subject_execution}
                          label={`Open subject evidence for ${item.case.case_key}`}
                        />
                      )}
                      {item.case.source_execution !== null && (
                        <SemanticExecutionLink
                          execution={item.case.source_execution}
                          label={`Open source evidence for ${item.case.case_key}`}
                        />
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
