import { ListApiKeysResponse, ListApiKeysResponseSchema } from '../schemas'

export async function fetchApiKeys(): Promise<ListApiKeysResponse> {
  const res = await fetch('/api/v1/api-keys', {
    method: 'GET',
    credentials: 'include',
  })
  if (!res.ok) {
    throw new Error(`Failed to list API keys (${res.status})`)
  }
  const json = await res.json()
  return ListApiKeysResponseSchema.parse(json)
}
