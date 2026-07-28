import type {
  EvaluationAttemptStatus,
  EvaluationRunStatus,
} from '../schemas/evaluation-runs'

type EvaluationStatus = EvaluationAttemptStatus | EvaluationRunStatus

const statusClassName: Record<EvaluationStatus, string> = {
  active:
    'bg-[var(--studio-outcome-cancelled-bg)] text-[var(--studio-outcome-cancelled)]',
  queued:
    'bg-[var(--studio-outcome-cancelled-bg)] text-[var(--studio-outcome-cancelled)]',
  completed:
    'bg-[var(--studio-outcome-completed-bg)] text-[var(--studio-outcome-completed)]',
  passed:
    'bg-[var(--studio-outcome-completed-bg)] text-[var(--studio-outcome-completed)]',
  failed:
    'bg-[var(--studio-outcome-failed-bg)] text-[var(--studio-outcome-failed)]',
  error:
    'bg-[var(--studio-outcome-failed-bg)] text-[var(--studio-outcome-failed)]',
}

export function EvaluationStatusBadge({ status }: { status: EvaluationStatus }) {
  return (
    <span className={`${statusClassName[status]} inline-flex rounded-full px-2.5 py-1 text-xs font-semibold`}>
      {status}
    </span>
  )
}
