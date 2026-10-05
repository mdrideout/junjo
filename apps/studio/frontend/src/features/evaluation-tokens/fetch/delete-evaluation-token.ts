export async function deleteEvaluationToken(tokenId: string): Promise<void> {
  const response = await fetch(
    `/api/v1/evaluation-tokens/${encodeURIComponent(tokenId)}`,
    {
      method: 'DELETE',
      credentials: 'include',
    },
  )
  if (!response.ok) {
    throw new Error(`Failed to delete access token (${response.status})`)
  }
}
