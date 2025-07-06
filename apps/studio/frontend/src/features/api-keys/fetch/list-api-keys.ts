import { API_HOST } from '../../../config'
import { ListApiKeysResponse, ListApiKeysResponseSchema } from '../schemas'

export async function fetchApiKeys(): Promise<ListApiKeysResponse> {
  const res = await fetch(`${API_HOST}/api_keys`, {
    method: 'GET',
    credentials: 'include',
  })
  if (!res.ok) {
    throw new Error(`Failed to list API keys (${res.status})`)
  }
  const json = await res.json()
  return ListApiKeysResponseSchema.parse(json)
}
