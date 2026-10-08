export interface FlushWalResponse {
  success: boolean
  message: string
}

export async function flushWal(): Promise<FlushWalResponse> {
  const res = await fetch('/api/v1/admin/flush-wal', {
    method: 'POST',
    credentials: 'include',
  })
  if (!res.ok) {
    throw new Error(`Failed to flush WAL (${res.status})`)
  }
  return res.json()
}
