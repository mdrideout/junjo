import { AppLink } from '../../../components/navigation/app-link'
import { executionResolverPath } from '../../../util/telemetry-paths'
import type { SemanticExecutionReference } from '../schemas/evaluation-runs'

export function SemanticExecutionLink({
  execution,
  label,
}: {
  execution: SemanticExecutionReference
  label: string
}) {
  return (
    <AppLink to={executionResolverPath(execution)} aria-label={label}>
      {label}
    </AppLink>
  )
}
