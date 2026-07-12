import { getApiHost } from '../../../config'
import { ListApiKeysResponse, ListApiKeysResponseSchema } from '../schemas'

export async function fetchApiKeys(): Promise<ListApiKeysResponse> {
  const apiHost = getApiHost('/api_keys')
  const res = await fetch(`${apiHost}/api_keys`, {
    method: 'GET',
    credentials: 'include',
  })
  if (!res.ok) {
    throw new Error(`Failed to list API keys (${res.status})`)
  }
  const json = await res.json()
  return ListApiKeysResponseSchema.parse(json)
}
