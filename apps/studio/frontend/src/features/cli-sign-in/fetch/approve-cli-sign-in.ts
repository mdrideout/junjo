import { readApiError } from '../../../auth/api-error'
import { CliSignInApprovedSchema, type CliSignInApproved } from '../schemas'

/**
 * Approves the pending CLI sign-in with this user code and returns the token
 * Studio minted for it, or null when Studio has no such pending sign-in (404
 * or 422).
 */
export async function approveCliSignIn(
  userCode: string,
): Promise<CliSignInApproved | null> {
  const response = await fetch(
    `/api/v1/cli-sign-ins/${encodeURIComponent(userCode)}/approve`,
    { method: 'POST', credentials: 'include' },
  )
  if (response.status === 404 || response.status === 422) return null
  if (!response.ok) {
    throw new Error(await readApiError(response, 'Failed to approve CLI sign-in'))
  }
  return CliSignInApprovedSchema.parse(await response.json())
}
