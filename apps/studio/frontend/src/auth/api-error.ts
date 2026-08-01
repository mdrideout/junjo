interface ApiErrorResponse {
  detail?: string | Array<{ msg?: string; message?: string }>
  message?: string
}

export async function readApiError(
  response: Response,
  fallback: string,
): Promise<string> {
  let data: ApiErrorResponse | null = null
  try {
    data = (await response.json()) as ApiErrorResponse
  } catch {
    return `${fallback} (${response.status})`
  }

  if (data === null || typeof data !== 'object') {
    return `${fallback} (${response.status})`
  }
  if (Array.isArray(data.detail)) {
    const details = data.detail
      .map((error) => error.msg || error.message)
      .filter(Boolean)
      .join('. ')
    return details || 'Validation failed.'
  }
  if (data.detail) {
    return data.detail
  }
  if (data.message) {
    return data.message
  }
  return `${fallback} (${response.status})`
}

export function requestFailureMessage(error: unknown): string {
  if (error instanceof TypeError && error.message === 'Failed to fetch') {
    return 'Unable to reach Junjo AI Studio.'
  }
  return error instanceof Error ? error.message : 'An error occurred'
}
