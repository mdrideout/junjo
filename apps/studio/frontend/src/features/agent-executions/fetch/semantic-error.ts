import { AgentEvidenceErrorResponseSchema } from '../schemas/agent-execution'

export async function getAgentEvidenceErrorMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  if (response.status !== 409) return `${fallback} (${response.status})`
  const body = await response.json().catch(() => null)
  const semanticError = AgentEvidenceErrorResponseSchema.safeParse(body)

  if (!semanticError.success) return `${fallback} (${response.status})`

  const diagnostics = semanticError.data.diagnostics
    .map((diagnostic) => `${diagnostic.code} at ${diagnostic.path}`)
    .join('; ')
  return `${semanticError.data.code}: ${semanticError.data.message}${diagnostics ? ` — ${diagnostics}` : ''}`
}
