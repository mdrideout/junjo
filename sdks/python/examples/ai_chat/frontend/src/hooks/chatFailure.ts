import { ApiError } from '../api/client'

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
