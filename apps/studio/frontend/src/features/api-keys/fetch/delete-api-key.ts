import { getApiHost } from '../../../config'

export async function deleteApiKey(id: string): Promise<void> {
  const apiHost = getApiHost('/api_keys')
  const res = await fetch(`${apiHost}/api_keys/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) {
    throw new Error(`Failed to delete API key (${res.status})`)
  }
}
