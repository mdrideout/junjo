import type { EvaluationTokenScope } from './schemas'

/**
 * How Studio names and describes each developer access token scope. The
 * create-token dialog and the CLI sign-in approval page show these words.
 */
export const AVAILABLE_SCOPES: ReadonlyArray<{
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
