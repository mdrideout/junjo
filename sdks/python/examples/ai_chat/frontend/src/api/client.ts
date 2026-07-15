import { z } from 'zod'
import {
  ConversationsResponseSchema,
  CreateContactRequestSchema,
  CreateContactResponseSchema,
  CreateTurnRequestSchema,
  PublicConfigResponseSchema,
  TurnListResponseSchema,
  TurnProblemResponseSchema,
  TurnSchema,
  type ConversationsResponse,
  type CreateContactRequest,
  type CreateContactResponse,
  type CreateTurnRequest,
  type PublicConfig,
  type Turn,
  type TurnListResponse,
} from './schemas'

export function normalizeApiBaseUrl(value: string | undefined): string {
  if (value === undefined || value === '') return ''
  let parsed: URL
  try {
    parsed = new URL(value)
  } catch {
    throw new Error('VITE_API_BASE_URL must be an absolute HTTP origin.')
  }
  if (
    !['http:', 'https:'].includes(parsed.protocol)
    || parsed.username !== ''
    || parsed.password !== ''
    || parsed.pathname !== '/'
    || parsed.search !== ''
    || parsed.hash !== ''
  ) {
    throw new Error('VITE_API_BASE_URL must be an absolute HTTP origin.')
  }
  return parsed.origin
}

const DEFAULT_API_BASE_URL = 'http://localhost:26252'
const API_BASE_URL = normalizeApiBaseUrl(
  import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL,
)

function rejectAmbiguousUrlCharacters(value: string): void {
  if (value.includes('\\') || Array.from(value).some(character => {
    const code = character.charCodeAt(0)
    return code <= 0x1F || code === 0x7F
  })) {
    throw new Error('API URLs cannot contain backslashes or ASCII control characters.')
  }
}

export function resolveApiUrl(path: string, baseUrl = API_BASE_URL): string {
  rejectAmbiguousUrlCharacters(path)
  if (!path.startsWith('/') || path.startsWith('//')) {
    throw new Error('API paths must be root-relative and begin with one /.')
  }
  return `${baseUrl}${path}`
}

export function resolveApiAssetUrl(path: string, baseUrl = API_BASE_URL): string {
  rejectAmbiguousUrlCharacters(path)
  if (path.startsWith('/')) return resolveApiUrl(path, baseUrl)
  let absolute: URL
  try {
    absolute = new URL(path)
  } catch {
    throw new Error('API asset URLs must be root-relative or absolute HTTP URLs.')
  }
  if (!['http:', 'https:'].includes(absolute.protocol)) {
    throw new Error('API asset URLs must be root-relative or absolute HTTP URLs.')
  }
  if (absolute.username !== '' || absolute.password !== '') {
    throw new Error('API asset URLs cannot contain credentials.')
  }
  return absolute.href
}

export class ApiError extends Error {
  readonly status: number
  readonly turn: Turn | null
  readonly workflowRunId: string | null
  readonly agentRunId: string | null
  readonly terminationReason: string | null

  constructor(
    status: number,
    detail = `Chat API request failed (${status}).`,
    turn: Turn | null = null,
    workflowRunId: string | null = null,
    agentRunId: string | null = null,
    terminationReason: string | null = null,
  ) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.turn = turn
    this.workflowRunId = workflowRunId
    this.agentRunId = agentRunId
    this.terminationReason = terminationReason
  }
}

async function apiError(response: Response): Promise<ApiError> {
  let body: unknown
  try {
    body = await response.json()
  } catch {
    return new ApiError(response.status)
  }
  const parsed = TurnProblemResponseSchema.safeParse(body)
  if (!parsed.success) return new ApiError(response.status)
  return new ApiError(
    response.status,
    parsed.data.detail,
    parsed.data.turn ?? null,
    parsed.data.workflow_run_id ?? null,
    parsed.data.agent_run_id ?? null,
    parsed.data.termination_reason ?? null,
  )
}

async function requestJson<T>(
  path: string,
  schema: z.ZodType<T>,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(resolveApiUrl(path), init)
  if (!response.ok) throw await apiError(response)
  return schema.parse(await response.json())
}

export function getPublicConfig(signal?: AbortSignal): Promise<PublicConfig> {
  return requestJson('/api/config', PublicConfigResponseSchema, { signal })
}

export function getConversations(signal?: AbortSignal): Promise<ConversationsResponse> {
  return requestJson('/api/conversations', ConversationsResponseSchema, { signal })
}

export function createContact(request: CreateContactRequest): Promise<CreateContactResponse> {
  const body = CreateContactRequestSchema.parse(request)
  return requestJson('/api/contacts', CreateContactResponseSchema, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function getTurn(turnId: string, signal?: AbortSignal): Promise<Turn> {
  return requestJson(`/api/turns/${encodeURIComponent(turnId)}`, TurnSchema, { signal })
}

export async function getConversationTurns(
  conversationId: string,
  signal?: AbortSignal,
): Promise<TurnListResponse> {
  const id = encodeURIComponent(conversationId)
  const result = await requestJson(
    `/api/conversations/${id}/turns`,
    TurnListResponseSchema,
    { signal },
  )
  if (result.conversation_id !== conversationId) {
    throw new Error('Chat API returned turns for a different conversation.')
  }
  return result
}

export async function createTurn(
  conversationId: string,
  request: CreateTurnRequest,
): Promise<Turn> {
  const body = CreateTurnRequestSchema.parse(request)
  const id = encodeURIComponent(conversationId)
  const result = await requestJson(
    `/api/conversations/${id}/turns`,
    TurnSchema,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
  if (result.conversation_id !== conversationId) {
    throw new Error('Chat API returned a turn for a different conversation.')
  }
  return result
}
