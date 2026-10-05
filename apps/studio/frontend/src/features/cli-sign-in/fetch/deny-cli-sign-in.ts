import { readApiError } from '../../../auth/api-error'
import { UserResponseSchema, type UserResponse } from '../../../auth/response-schemas'

/**
 * Denies the pending CLI sign-in with this user code and returns Studio's
 * answer, or null when Studio has no such pending sign-in (404 or 422).
 */
export async function denyCliSignIn(
  userCode: string,
): Promise<UserResponse | null> {
  const response = await fetch(
    `/api/v1/cli-sign-ins/${encodeURIComponent(userCode)}/deny`,
    { method: 'POST', credentials: 'include' },
  )
  if (response.status === 404 || response.status === 422) return null
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to deny CLI sign-in'))
  }
  return UserResponseSchema.parse(await response.json())
}
