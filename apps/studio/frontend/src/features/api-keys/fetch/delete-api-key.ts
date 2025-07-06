import { API_HOST } from '../../../config'

export async function deleteApiKey(key: string): Promise<void> {
  const res = await fetch(`${API_HOST}/api_keys/${encodeURIComponent(key)}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) {
    throw new Error(`Failed to delete API key (${res.status})`)
  }
}
