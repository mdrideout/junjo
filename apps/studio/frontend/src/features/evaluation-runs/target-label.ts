import type { EvaluationTargetKind } from './schemas/evaluation-runs'

export function evaluationTargetLabel(
  kind: EvaluationTargetKind,
  name: string,
): string {
  const entity = kind[0].toUpperCase() + kind.slice(1)
  return `${entity} → ${name}`
}
