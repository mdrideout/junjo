import { AppLink } from '../../../components/navigation/app-link'
import { executionResolverPath, tracesPath } from '../../../util/telemetry-paths'
import type { ExecutionEvidenceReference } from '../schemas/evaluation-runs'

export function ExecutionEvidenceLink({
  evidence,
  label,
}: {
  evidence: ExecutionEvidenceReference
  label: string
}) {
  const destination =
    evidence.kind === 'junjo_execution'
      ? executionResolverPath(evidence)
      : tracesPath(evidence.service_name, evidence.trace_id, evidence.span_id)

  return (
    <AppLink to={destination} aria-label={label}>
      {label}
    </AppLink>
  )
}
