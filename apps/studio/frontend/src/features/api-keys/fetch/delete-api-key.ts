export async function deleteApiKey(id: string): Promise<void> {
  const res = await fetch(`/api/v1/api-keys/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) {
    throw new Error(`Failed to delete API key (${res.status})`)
  }
}
