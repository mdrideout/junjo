import { ApiError } from '../api/client'
import type { Turn } from '../api/schemas'

export interface ChatFailure {
  message: string
  workflowRunId: string | null
  agentRunId: string | null
  terminationReason: string | null
}

export function failureFrom(error: unknown): ChatFailure {
  return {
    message: error instanceof Error ? error.message : 'The chat request failed.',
    workflowRunId: error instanceof ApiError ? error.workflowRunId : null,
    agentRunId: error instanceof ApiError ? error.agentRunId : null,
    terminationReason: error instanceof ApiError ? error.terminationReason : null,
  }
}

export function failureFromTurn(turn: Turn): ChatFailure | null {
  if (turn.failure === null) return null
  return {
    message: turn.failure.detail,
    workflowRunId: turn.execution_references.workflow_run_id,
    agentRunId: turn.execution_references.agent_run_id,
    terminationReason: turn.failure.termination_reason,
  }
}
