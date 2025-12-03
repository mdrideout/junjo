import { getApiHost } from '../../../config'

export interface FlushWalResponse {
  success: boolean
  message: string
}

export async function flushWal(): Promise<FlushWalResponse> {
  const apiHost = getApiHost('/api/admin/flush-wal')
  const res = await fetch(`${apiHost}/api/admin/flush-wal`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!res.ok) {
    throw new Error(`Failed to flush WAL (${res.status})`)
  }
  return res.json()
}
